"""
Smart Scheduler for Water Heater Control

Computes optimal heating slots based on Octopus Agile rates rather than
time windows. The algorithm:
1. Fetches rates for the next 24-48 hours
2. Prefers rates below the configured price ceiling
3. Excludes blocked hours (e.g., evening peak)
4. Preserves the morning/afternoon/evening hot-water windows
5. If prices are high overall, fills the configured daily allowance with
   the cheapest unblocked slots rather than leaving the tank unheated
"""

import logging
from datetime import datetime, timedelta, timezone
import pytz

logger = logging.getLogger(__name__)


class SmartScheduler:
    """
    Computes optimal heating slots based on electricity rates.
    """

    def __init__(self, config):
        self.config = config
        # pytz is already an application dependency and bundles the IANA zone
        # database on Windows as well as Linux.  This keeps local development
        # and Railway on the same Europe/London DST rules.
        self.timezone = pytz.timezone(getattr(config, 'LOCAL_TIMEZONE', 'Europe/London'))
        self.last_schedule_computation = None
        self.last_rate_check = None
        self.tomorrow_scheduled = False
        self.current_schedule = []

    def _local_start(self, slot):
        """Return a rate slot's start in the configured household timezone."""
        return slot['valid_from'].astimezone(self.timezone)

    def compute_schedule_for_date(
        self,
        target_date,
        rates,
        budget_hours,
        max_price,
        use_below_average,
        blocked_hours,
        not_before=None,
    ):
        """Select the best tariff slots for one local calendar date.

        ``max_price`` is a preferred ceiling, not a reason to leave the tank
        cold. Readiness windows and the remaining daily allowance first use
        preferred-price slots, then the cheapest unblocked rates available.
        Blocked hours remain an absolute exclusion.
        """
        if not rates:
            logger.warning("No rates provided to scheduler.")
            return []

        daily_rates = [r for r in rates if self._local_start(r).date() == target_date]
        if not_before is not None:
            # A same-day recomputation must not spend the daily allowance on
            # morning/afternoon slots that have already elapsed.
            daily_rates = [r for r in daily_rates if r['valid_to'] > not_before]
        if not daily_rates:
            logger.warning(f"No rates found for target date: {target_date}")
            return []

        daily_avg = sum(r['value_inc_vat'] for r in daily_rates) / len(daily_rates)
        strict_threshold = min(daily_avg, max_price) if use_below_average else max_price
        preferred_cap = max_price
        target_slots = max(0, int(budget_hours * 2))

        logger.info(
            "Smart Scheduler [%s]: Daily avg=%.2fp, Strict Threshold=%.2fp, "
            "Preferred Cap=%.2fp, Target=%s slots",
            target_date,
            daily_avg,
            strict_threshold,
            preferred_cap,
            target_slots,
        )

        unblocked_rates = []
        above_cap = []
        rejected_blocked = []
        for slot in daily_rates:
            if self._local_start(slot).hour in blocked_hours:
                rejected_blocked.append(slot)
                continue
            unblocked_rates.append(slot)
            if slot['value_inc_vat'] > preferred_cap:
                above_cap.append(slot)

        preferred_rates = [s for s in unblocked_rates if s['value_inc_vat'] <= preferred_cap]
        selected = []
        selected_ids = set()
        fallback_selected = []

        def slot_id(slot):
            return slot['valid_from']

        def price_then_time(slot):
            return (slot['value_inc_vat'], self._local_start(slot))

        def price_then_later(slot):
            return (slot['value_inc_vat'], -self._local_start(slot).timestamp())

        def take(candidates, count, sort_key):
            capacity = min(max(0, count), max(0, target_slots - len(selected)))
            if capacity == 0:
                return []
            available = [s for s in candidates if slot_id(s) not in selected_ids]
            available.sort(key=sort_key)
            chosen = available[:capacity]
            for slot in chosen:
                selected.append(slot)
                selected_ids.add(slot_id(slot))
            return chosen

        def fill_readiness_window(predicate, quota, sort_key, label):
            needed = min(quota, max(0, target_slots - len(selected)))
            if needed == 0:
                return

            window_all = [s for s in unblocked_rates if predicate(self._local_start(s))]
            if not window_all:
                logger.warning("No %s rate data is available for the readiness window.", label.lower())
                return

            window_preferred = [s for s in window_all if s['value_inc_vat'] <= preferred_cap]
            preferred_chosen = take(window_preferred, needed, sort_key)
            remaining = needed - len(preferred_chosen)
            if remaining > 0:
                fallback = take(window_all, remaining, sort_key)
                fallback_selected.extend(fallback)
                over_cap_count = sum(s['value_inc_vat'] > preferred_cap for s in fallback)
                if fallback:
                    logger.warning(
                        "%s hot-water fallback selected %s extra slot(s); %s are above "
                        "the preferred %.2fp cap.",
                        label,
                        len(fallback),
                        over_cap_count,
                        preferred_cap,
                    )

        # Preserve readiness priorities without exceeding the daily allowance.
        fill_readiness_window(
            lambda local: 0 <= local.hour < 6,
            4,
            price_then_later,
            "Morning",
        )
        fill_readiness_window(
            lambda local: 14 <= local.hour < 16,
            2,
            price_then_time,
            "Afternoon",
        )
        fill_readiness_window(
            lambda local: 19 <= local.hour < 23 or (local.hour == 23 and local.minute < 30),
            2,
            price_then_time,
            "Evening",
        )

        # Fill discretionary capacity with rates that satisfy the strict
        # preference (below daily average and/or the configured ceiling).
        remaining = target_slots - len(selected)
        strict_candidates = [
            s for s in preferred_rates if s['value_inc_vat'] <= strict_threshold
        ]
        take(strict_candidates, remaining, price_then_later)

        # If preferences cannot supply the daily allowance, use the cheapest
        # remaining unblocked slots. This prevents a zero-heating day.
        remaining = target_slots - len(selected)
        if remaining > 0:
            fallback = take(unblocked_rates, remaining, price_then_later)
            fallback_selected.extend(fallback)

        selected.sort(key=lambda s: s['valid_from'])
        self.last_schedule_computation = datetime.now(timezone.utc)

        if len(selected) < target_slots:
            logger.warning(
                "Only %s/%s requested heating slots could be scheduled because "
                "the tariff response contained too few unblocked rows.",
                len(selected),
                target_slots,
            )

        self._log_schedule_summary(
            target_date,
            selected,
            above_cap,
            rejected_blocked,
            strict_threshold,
            preferred_cap,
            daily_avg,
            target_slots,
            fallback_selected,
        )
        return selected

    def _log_schedule_summary(
        self,
        target_date,
        selected,
        above_cap,
        rejected_blocked,
        threshold,
        preferred_cap,
        daily_avg,
        target_slots,
        fallback_selected,
    ):
        """Logs a clear summary of the computed schedule."""
        logger.info("=" * 60)
        logger.info(f"SMART SCHEDULE COMPUTED FOR {target_date}")
        logger.info("=" * 60)
        logger.info(f"Daily Average: {daily_avg:.2f}p | Price Threshold: {threshold:.2f}p")
        logger.info(
            "Scheduled: %.1f / %.1f hours (%s/%s x 30-min slots)",
            len(selected) * 0.5,
            target_slots * 0.5,
            len(selected),
            target_slots,
        )
        logger.info("")

        if selected:
            logger.info("SELECTED HEATING SLOTS:")
            total_cost = 0
            for slot in selected:
                time_str = slot['valid_from'].strftime('%Y-%m-%d %H:%M')
                price = slot['value_inc_vat']
                total_cost += price
                logger.info(f"  [ON] {time_str} - {price:.2f}p")

            avg_cost = total_cost / len(selected)
            logger.info(f"\nAverage slot price: {avg_cost:.2f}p")
            # Each tariff row is 30 minutes, so a 3 kW element consumes at
            # most 1.5 kWh per selected slot before its thermostat cuts out.
            logger.info(f"Estimated heating cost: {(total_cost * 1.5 / 100):.2f} GBP (assuming 3kW heater)")
        elif target_slots == 0:
            logger.info("No slots selected because the configured daily allowance is zero.")
        else:
            logger.warning("NO SLOTS SELECTED - no unblocked rate data is available for this date.")

        selected_above_cap = [s for s in selected if s['value_inc_vat'] > preferred_cap]
        if selected_above_cap:
            prices = [s['value_inc_vat'] for s in selected_above_cap]
            logger.warning(
                "\nPRICE-CAP FALLBACK ACTIVE: %s selected slot(s) exceed %.1fp "
                "(range %.2f-%.2fp)",
                len(selected_above_cap),
                preferred_cap,
                min(prices),
                max(prices),
            )
        elif fallback_selected:
            logger.info(
                "Price-preference fallback used %s slot(s) above the strict %.1fp threshold.",
                len(fallback_selected),
                threshold,
            )

        if above_cap:
            logger.info(f"\nAvailable above preferred {preferred_cap:.1f}p cap: {len(above_cap)} slots")

        if rejected_blocked:
            logger.info(f"Rejected (blocked hours): {len(rejected_blocked)} slots")

        logger.info("=" * 60)

    def should_check_for_new_rates(self, current_time, publish_window_start, publish_window_end):
        """
        Determines if we should check for new rates based on time of day.

        During the rate publication window (typically 15:00-19:00 UTC), check every 15 minutes.
        Outside that window, check every 2 hours.

        Returns:
            (should_check: bool, reason: str)
        """
        hour = current_time.hour

        # First check ever
        if self.last_rate_check is None:
            return True, "Initial rate fetch"

        time_since_check = (current_time - self.last_rate_check).total_seconds()

        # During rate publication window, check more frequently
        if publish_window_start <= hour < publish_window_end:
            if time_since_check >= 900:  # 15 minutes
                return True, f"Rate publication window (every 15 min)"
            return False, "Waiting (publication window, checked recently)"

        # Outside window, check every 2 hours
        if time_since_check >= 7200:  # 2 hours
            return True, "Periodic check (every 2 hours)"

        return False, "Waiting for next check interval"

    def has_tomorrow_rates(self, rates, current_time):
        """Check if we have rates for tomorrow."""
        local_now = current_time.astimezone(self.timezone)
        tomorrow = (local_now + timedelta(days=1)).date()
        return any(self._local_start(r).date() == tomorrow for r in rates)

    def mark_rate_check(self, current_time):
        """Record that we just checked rates."""
        self.last_rate_check = current_time

    def mark_tomorrow_scheduled(self):
        """Record that tomorrow's schedule has been computed."""
        self.tomorrow_scheduled = True

    def reset_daily_flags(self):
        """Reset flags at midnight."""
        self.tomorrow_scheduled = False

    def get_schedule_for_display(self):
        """Returns schedule data formatted for UI display."""
        return {
            "slots": self.current_schedule,
            "computed_at": self.last_schedule_computation.isoformat() if self.last_schedule_computation else None,
            "slot_count": len(self.current_schedule),
            "total_hours": len(self.current_schedule) * 0.5
        }

