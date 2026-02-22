"""
Smart Scheduler for Water Heater Control

Computes optimal heating slots based on Octopus Agile rates rather than
time windows. The algorithm:
1. Fetches rates for the next 24-48 hours
2. Applies price threshold (below average AND/OR absolute cap)
3. Excludes blocked hours (e.g., morning peak)
4. Selects the cheapest N slots to meet the daily heating budget
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SmartScheduler:
    """
    Computes optimal heating slots based on electricity rates.
    """

    def __init__(self, config):
        self.config = config
        self.last_schedule_computation = None
        self.last_rate_check = None
        self.tomorrow_scheduled = False
        self.current_schedule = []

    def compute_schedule_for_date(self, target_date, rates, budget_hours, max_price, use_below_average, blocked_hours):
        """
        Main algorithm to select optimal heating slots for a specific calendar date.

        Args:
            target_date: datetime.date object representing the day to schedule
            rates: List of rate dicts with 'valid_from', 'valid_to', 'value_inc_vat'
            budget_hours: Total hours of heating needed (e.g., 4.0)
            max_price: Absolute maximum price in pence (e.g., 30.0)
            use_below_average: If True, also requires price to be below daily average
            blocked_hours: List of hours to never heat during (e.g., [7, 8] for 07:00-09:00)

        Returns:
            List of selected rate slots for the target_date, sorted chronologically
        """
        if not rates:
            logger.warning("No rates provided to scheduler.")
            return []

        # Filter rates to only match the target_date
        daily_rates = [r for r in rates if r['valid_from'].date() == target_date]

        if not daily_rates:
            logger.warning(f"No rates found for target date: {target_date}")
            return []

        # Calculate daily average
        daily_avg = sum(r['value_inc_vat'] for r in daily_rates) / len(daily_rates)

        # Determine price thresholds
        strict_threshold = min(daily_avg, max_price) if use_below_average else max_price
        hard_limit = max_price

        logger.info(f"Smart Scheduler [{target_date}]: Daily avg={daily_avg:.2f}p, Strict Threshold={strict_threshold:.2f}p, Hard Limit={hard_limit:.2f}p")

        # Filter eligible slots (HARD LIMIT ONLY)
        eligible = []
        rejected_expensive = []
        rejected_blocked = []

        for slot in daily_rates:
            hour = slot['valid_from'].hour

            # Check if hour is blocked
            if hour in blocked_hours:
                rejected_blocked.append(slot)
                continue

            # Check price threshold (Hard Limit)
            if slot['value_inc_vat'] > hard_limit:
                rejected_expensive.append(slot)
                continue

            eligible.append(slot)

        # Calculate how many slots we need
        total_slots_needed = int(budget_hours * 2)
        afternoon_slots_needed = 2 # 1 Hour
        evening_slots_needed = 2 # 1 Hour for Evening Boost

        # --- STEP 1: Secure Afternoon Boost (14:00 - 16:00) ---
        afternoon_candidates = []
        for slot in eligible:
            h = slot['valid_from'].hour
            if 14 <= h < 16:
                afternoon_candidates.append(slot)
        
        afternoon_candidates.sort(key=lambda s: s['value_inc_vat'])
        selected_afternoon = afternoon_candidates[:afternoon_slots_needed]

        # --- STEP 2: Secure Evening Boost (19:00 - 23:30) ---
        evening_candidates = []
        for slot in eligible:
            h = slot['valid_from'].hour
            m = slot['valid_from'].minute
            if 19 <= h < 23 or (h == 23 and m < 30):
                if slot not in selected_afternoon:
                    evening_candidates.append(slot)
        
        evening_candidates.sort(key=lambda s: s['value_inc_vat'])
        selected_evening = evening_candidates[:evening_slots_needed]

        # --- STEP 3: Fill Logic (Night/Rest of Day) ---
        remaining_slots_count = total_slots_needed - len(selected_afternoon) - len(selected_evening)
        if remaining_slots_count < 0:
            remaining_slots_count = 0
        
        selected_ids = {f"{s['valid_from']}" for s in selected_afternoon + selected_evening}
        
        remaining_candidates = [
            s for s in eligible 
            if f"{s['valid_from']}" not in selected_ids 
            and s['value_inc_vat'] <= strict_threshold
        ]
        
        def effective_price(slot):
            price = slot['value_inc_vat']
            hour_index = slot['valid_from'].hour
            return price - (0.01 * hour_index)

        remaining_candidates.sort(key=effective_price)
        selected_rest = remaining_candidates[:remaining_slots_count]
        
        # Combine
        final_selection = selected_afternoon + selected_evening + selected_rest
        final_selection.sort(key=lambda s: s['valid_from'])
        
        self._log_schedule_summary(target_date, final_selection, rejected_expensive, rejected_blocked, strict_threshold, daily_avg)
        
        return final_selection

    def _log_schedule_summary(self, target_date, selected, rejected_expensive, rejected_blocked, threshold, daily_avg):
        """Logs a clear summary of the computed schedule."""
        logger.info("=" * 60)
        logger.info(f"SMART SCHEDULE COMPUTED FOR {target_date}")
        logger.info("=" * 60)
        logger.info(f"Daily Average: {daily_avg:.2f}p | Price Threshold: {threshold:.2f}p")
        logger.info(f"Budget: {len(selected) * 0.5:.1f} hours ({len(selected)} x 30-min slots)")
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
            logger.info(f"Estimated heating cost: {(total_cost * 3 / 100):.2f} GBP (assuming 3kW heater)")
        else:
            logger.warning("NO SLOTS SELECTED - Check configuration!")

        if rejected_expensive:
            logger.info(f"\nRejected (above {threshold:.1f}p): {len(rejected_expensive)} slots")

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
        tomorrow = (current_time + timedelta(days=1)).date()
        return any(r['valid_from'].date() == tomorrow for r in rates)

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
