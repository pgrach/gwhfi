import time
import logging
import schedule
from datetime import datetime, timedelta, timezone
from config import Config
from services.time_service import TimeService
from services.shelly_manager import ShellyManager
from services.smart_scheduler import SmartScheduler
from services.schedule_storage import ScheduleStorage
from services.thermostat_cycle_detector import DetectorConfig, ThermostatCycleDetector
from services.thermostat_state_storage import ThermostatStateStorage
from tuya_manager import TuyaManager
from octopus_client import OctopusClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("smart_water.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SmartWaterController:
    def __init__(self, dry_run=None):
        self.dry_run = Config.DRY_RUN if dry_run is None else dry_run
        logger.info(f"Initializing Smart Water Controller (Dry Run: {self.dry_run})")

        if not Config.validate_shelly_control_routing():
            raise SystemExit(
                "Unsafe Shelly configuration: the single relay cannot control both heater routes."
            )

        self.time_service = TimeService(Config.LOCAL_TIMEZONE)
        
        self.tuya = TuyaManager()
        if not getattr(self.tuya, 'enabled', True):
            logger.warning("Tuya Manager disabled due to missing config.")
            
        self.shelly = ShellyManager()
        if not self.shelly.enabled:
            logger.warning("Shelly Manager disabled. Thermostat inference will NOT function.")
        
        self.octopus = OctopusClient(Config.OCTOPUS_PRODUCT_CODE, Config.OCTOPUS_REGION_CODE)
        self.scheduler = SmartScheduler(Config)
        self.schedule_storage = ScheduleStorage()

        self.main_heater_slots = []
        self.second_heater_slots = []
        
        self.cooldown_until = None  # live-mode compatibility for command logging
        self.thermostat_detector = None
        self.thermostat_state_storage = None
        self.thermostat_mode = Config.THERMOSTAT_CONTROL_MODE
        thermostat_route_valid = (
            Config.OFF_PEAK_HEATER_TARGET == 'second'
            and Config.SECOND_HEATER_CONTROL == 'shelly'
            and self.shelly.monitoring_enabled
        )
        if self.thermostat_mode != 'off' and not thermostat_route_valid:
            logger.warning(
                "Thermostat inference requested but disabled: it requires the "
                "off-peak second heater on Shelly control plus Shelly meter telemetry."
            )
            self.thermostat_mode = 'off'
        elif self.thermostat_mode != 'off':
            self.thermostat_state_storage = ThermostatStateStorage(
                site_id=Config.TELEMETRY_SITE_ID,
                heater_key="off_peak",
            )
            restored_state = None
            # Shadow state must never survive a deployment and accidentally
            # become a live suppression decision later.
            if self.thermostat_mode == 'live':
                restored_state = self.thermostat_state_storage.load_state(live_only=True)
            self.thermostat_detector = ThermostatCycleDetector(
                DetectorConfig(
                    on_threshold_w=Config.THERMOSTAT_POWER_ON_THRESHOLD_W,
                    off_threshold_w=Config.THERMOSTAT_POWER_OFF_THRESHOLD_W,
                    min_real_heat_minutes=Config.THERMOSTAT_MIN_REAL_HEAT_MINUTES,
                    min_real_heat_wh=Config.THERMOSTAT_MIN_REAL_HEAT_WH,
                    low_samples_required=Config.THERMOSTAT_LOW_SAMPLES_REQUIRED,
                    chatter_window_minutes=Config.THERMOSTAT_CHATTER_WINDOW_MINUTES,
                    min_chatter_transitions=Config.THERMOSTAT_MIN_CHATTER_TRANSITIONS,
                    max_topup_burst_minutes=Config.THERMOSTAT_MAX_TOPUP_BURST_MINUTES,
                    min_cooldown_minutes=Config.THERMOSTAT_MIN_COOLDOWN_MINUTES,
                    max_deferral_minutes=Config.THERMOSTAT_MAX_DEFERRAL_MINUTES,
                    probe_success_minutes=Config.THERMOSTAT_PROBE_SUCCESS_MINUTES,
                    probe_short_minutes=Config.THERMOSTAT_PROBE_SHORT_MINUTES,
                    max_sample_gap_minutes=Config.THERMOSTAT_MAX_SAMPLE_GAP_MINUTES,
                ),
                initial_state=restored_state,
            )

        # State storage for UI
        self.system_state = {
            "peak_heater": {"online": False, "state": "UNKNOWN", "last_error": None},
            "off_peak_heater": {"online": False, "state": "UNKNOWN", "last_error": None},
            "cooldown_mode": False,
            "cooldown_until": None,
            "thermostat_control": {
                "mode": self.thermostat_mode,
                "state": self.thermostat_detector.state if self.thermostat_detector else "OFF",
                "suppressed": False,
                "reason": None,
                "hold_until": None,
                "evidence": {},
            },
            "last_updated": None,
            "next_schedule_update": None,
            "rates": []
        }
        
        # Verify clock on startup
        offset, safe = self.time_service.check_system_clock()
        if not safe:
            logger.error("System clock is unreliable! Aborting startup.")
            raise SystemExit("Unreliable system clock")

    def should_update_schedule(self):
        """
        Determines if we should check for new rates based on time of day.
        During rate publication window (15:00-19:00 UTC), check every 15 minutes.
        Outside that window, check every 2 hours.
        """
        now = self.time_service.now()
        should_check, reason = self.scheduler.should_check_for_new_rates(
            now,
            Config.RATE_PUBLISH_WINDOW_START,
            Config.RATE_PUBLISH_WINDOW_END
        )
        if should_check:
            logger.debug(f"Rate check triggered: {reason}")
        return should_check

    def update_schedule(self):
        """
        Fetches rates and calculates heating slots using Smart Scheduler.
        Replaces the old fixed 3-Window Strategy with dynamic rate-based scheduling.
        """
        now = self.time_service.now()
        today = self.time_service.get_local_time().date()
        tomorrow = today + timedelta(days=1)

        # Reset daily flags at midnight
        if now.hour == 0 and now.minute < 2:
            self.scheduler.reset_daily_flags()

        logger.info("Fetching rates from Octopus Energy...")
        rates = self.octopus.get_rates()

        if not rates:
            logger.error("Failed to fetch rates. Retaining existing schedule.")
            return

        self.scheduler.mark_rate_check(now)

        # Filter to future rates only for free heater
        future_rates = [r for r in rates if r['valid_to'] > now]

        if not rates:
            logger.warning("No rates available. Waiting for next update.")
            return

        # Check if we have tomorrow's rates
        has_tomorrow = self.scheduler.has_tomorrow_rates(rates, now)

        if has_tomorrow and not self.scheduler.tomorrow_scheduled:
            logger.info("Tomorrow's rates are now available! Computing optimized schedule...")
            self.scheduler.mark_tomorrow_scheduled()

        # Compute optimal slots using Smart Scheduler for today and tomorrow separately
        today_slots = self.scheduler.compute_schedule_for_date(
            target_date=today,
            rates=rates,
            budget_hours=Config.DAILY_HEATING_BUDGET_HOURS,
            max_price=Config.ABSOLUTE_MAX_PRICE,
            use_below_average=Config.USE_BELOW_AVERAGE,
            blocked_hours=Config.BLOCKED_HOURS,
            not_before=now,
        )
        
        tomorrow_slots = []
        if has_tomorrow:
            tomorrow_slots = self.scheduler.compute_schedule_for_date(
                target_date=tomorrow,
                rates=rates,
                budget_hours=Config.DAILY_HEATING_BUDGET_HOURS,
                max_price=Config.ABSOLUTE_MAX_PRICE,
                use_below_average=Config.USE_BELOW_AVERAGE,
                blocked_hours=Config.BLOCKED_HOURS
            )

        self.main_heater_slots = today_slots + tomorrow_slots
        self.scheduler.current_schedule = self.main_heater_slots

        # Peak Heater: Negative/free rate strategy (unchanged, uses future_rates)
        self.second_heater_slots = self.octopus.get_negative_rates(
            future_rates, Config.SECOND_HEATER_THRESHOLD
        )

        # Replace the complete local today/tomorrow window so stale green dots
        # cannot survive when a recomputation selects fewer (or zero) slots.
        local_start = self.time_service.timezone.localize(datetime.combine(today, datetime.min.time()))
        local_end = self.time_service.timezone.localize(datetime.combine(tomorrow + timedelta(days=1), datetime.min.time()))
        replace_from = local_start.astimezone(timezone.utc)
        replace_to = local_end.astimezone(timezone.utc)
        off_peak_saved = self.schedule_storage.save_schedule(
            self.main_heater_slots,
            heater_type="off_peak",
            replace_from=replace_from,
            replace_to=replace_to,
        )
        peak_saved = self.schedule_storage.save_schedule(
            self.second_heater_slots,
            heater_type="peak",
            replace_from=replace_from,
            replace_to=replace_to,
        )
        if self.schedule_storage.enabled and not (off_peak_saved and peak_saved):
            logger.error(
                "Schedule persistence failed; the dashboard markers may not match "
                "the controller's in-memory schedule."
            )

        # Update UI state
        self.system_state["rates"] = rates
        self.system_state["schedule"] = self.scheduler.get_schedule_for_display()
        self.system_state["next_schedule_update"] = self._get_next_schedule_check_time(now)

    def _get_next_schedule_check_time(self, now):
        """Calculate when the next schedule check will occur."""
        hour = now.hour
        if Config.RATE_PUBLISH_WINDOW_START <= hour < Config.RATE_PUBLISH_WINDOW_END:
            next_check = now + timedelta(minutes=15)
        else:
            next_check = now + timedelta(hours=2)
        return next_check.strftime("%H:%M")

    def is_in_slot(self, slots, current_time):
        """Checks if current_time is within any of the provided slots."""
        for slot in slots:
            if slot['valid_from'] <= current_time < slot['valid_to']:
                return True, slot
        return False, None

    def control_loop(self):
        """Main check logic."""
        now_utc = self.time_service.now()
        self.system_state["last_updated"] = now_utc.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Work out which schedule windows are active.
        active_peak, slot_peak = self.is_in_slot(self.second_heater_slots, now_utc)
        active_offpeak, slot_offpeak = self.is_in_slot(self.main_heater_slots, now_utc)

        # 2. Infer mechanical-thermostat saturation.  All errors fail open so
        # detector or persistence faults can never prevent the Shelly lease
        # from being renewed during a valid heating slot.
        active_offpeak, slot_offpeak = self.apply_thermostat_policy(
            active_offpeak,
            slot_offpeak,
            now_utc,
        )

        # 3. Apply controls. Normal setup routes off-peak scheduled slots to the lower/storage heater.
        # The main-heater route is available as an explicit fallback when configured.
        if Config.OFF_PEAK_HEATER_TARGET == 'main':
            active_main = active_peak or active_offpeak
            main_slot = slot_peak if active_peak else slot_offpeak
            main_name = "Main Heater (Peak/Off-Peak)"
            self.apply_heater_state("peak_heater", Config.TUYA_DEVICE_ID_MAIN, active_main, main_name, main_slot)

            if Config.STORAGE_HEATER_ENABLED:
                logger.info("Storage heater enabled but OFF_PEAK_HEATER_TARGET=main, so storage heater is not controlled.")
            else:
                self.system_state["off_peak_heater"]["online"] = False
                self.system_state["off_peak_heater"]["state"] = "DISABLED"
                self.system_state["off_peak_heater"]["last_error"] = "Storage heater disabled by config; off-peak slots routed to main heater."
        else:
            # Peak heater ignores cooldown logic because it is the free/negative-price strategy.
            self.apply_heater_state("peak_heater", Config.TUYA_DEVICE_ID_MAIN, active_peak, "Peak Heater", slot_peak)
            self.apply_heater_state("off_peak_heater", Config.TUYA_DEVICE_ID_SECOND, active_offpeak, "Off-Peak Heater", slot_offpeak)

    def apply_thermostat_policy(self, active_offpeak, slot_offpeak, now_utc):
        """Run thermostat inference and optionally suppress the storage relay."""
        self.system_state["cooldown_mode"] = False
        self.system_state["cooldown_until"] = None
        self.cooldown_until = None

        detector = self.thermostat_detector
        if detector is None:
            return active_offpeak, slot_offpeak

        state_before = detector.state
        detector_state_before = detector.export_state()
        reading = None
        relay_state = self.system_state["off_peak_heater"]
        relay_confirmed_on = bool(
            relay_state.get("online") and relay_state.get("state") == "ON"
        )
        # While virtually holding, do not interpret the real shadow-mode load;
        # this mirrors the samples that live mode would see with its relay OFF.
        should_sample = active_offpeak and state_before != "HOLD" and relay_confirmed_on
        try:
            if should_sample:
                reading = self.shelly.get_meter_reading(channel=Config.SHELLY_CHANNEL_SECOND)
            power_w = reading.get("power_w") if reading else None
            energy_total_wh = reading.get("energy_total_wh") if reading else None
            decision = detector.observe(
                now=now_utc,
                scheduled_on=active_offpeak,
                relay_commanded_on=(
                    active_offpeak and state_before != "HOLD" and relay_confirmed_on
                ),
                power_w=power_w,
                energy_total_wh=energy_total_wh,
                sample_valid=reading is not None,
            )
        except Exception:
            logger.exception("Thermostat detector failed; continuing scheduled heating (fail open).")
            return active_offpeak, slot_offpeak

        shadow_mode = self.thermostat_mode == "shadow"
        live_mode = self.thermostat_mode == "live"
        state_after = decision.state
        event_type = decision.event
        if event_type is None and state_before != state_after:
            event_type = "state_transition"

        control_state = self.system_state["thermostat_control"]
        control_state.update({
            "mode": self.thermostat_mode,
            "state": state_after,
            "suppressed": bool(live_mode and decision.suppress and active_offpeak),
            "reason": decision.reason,
            "hold_until": decision.hold_until.isoformat() if decision.hold_until else None,
            "evidence": decision.evidence,
        })

        if event_type:
            prefix = "SHADOW" if shadow_mode else "LIVE"
            logger.info(
                "THERMOSTAT %s event=%s state=%s->%s reason=%s evidence=%s",
                prefix,
                event_type,
                state_before,
                state_after,
                decision.reason,
                decision.evidence,
            )
            transition_persisted = False
            try:
                if self.thermostat_state_storage:
                    transition_persisted = self.thermostat_state_storage.save_transition(
                        occurred_at=now_utc,
                        state_payload=detector.export_state(),
                        mode_before=state_before,
                        mode_after=state_after,
                        event_type=event_type,
                        shadow_mode=shadow_mode,
                        relay_commanded_on=active_offpeak,
                        power_w=power_w,
                        energy_total_wh=energy_total_wh,
                        evidence={**decision.evidence, "reason": decision.reason},
                        policy_version=Config.THERMOSTAT_POLICY_VERSION,
                        slot=slot_offpeak,
                    )
            except Exception:
                logger.exception("Thermostat transition persistence failed.")

            if live_mode and decision.suppress and not transition_persisted:
                # Never turn a scheduled heater off for a state transition we
                # could not durably record. Restore the pre-observation state
                # so the next loop retries the evidence and keeps renewing the
                # bounded Shelly ON lease in the meantime.
                detector.restore_state(detector_state_before)
                control_state.update({
                    "state": detector.state,
                    "suppressed": False,
                    "reason": "transition_persistence_failed",
                    "hold_until": (
                        detector.hold_until.isoformat() if detector.hold_until else None
                    ),
                    "evidence": {},
                })
                logger.error(
                    "Thermostat suppression skipped because its transition was not persisted."
                )
                return active_offpeak, slot_offpeak

        if decision.suppress and active_offpeak:
            if shadow_mode:
                logger.info(
                    "THERMOSTAT SHADOW would suppress off-peak heating until %s (%s).",
                    decision.hold_until,
                    decision.reason,
                )
            elif live_mode:
                self.cooldown_until = decision.hold_until
                self.system_state["cooldown_mode"] = True
                self.system_state["cooldown_until"] = (
                    decision.hold_until.isoformat() if decision.hold_until else None
                )
                return False, None

        return active_offpeak, slot_offpeak

    def _heater_backend(self, key):
        return Config.MAIN_HEATER_CONTROL if key == "peak_heater" else Config.SECOND_HEATER_CONTROL

    def _heater_relay_channel(self, key):
        if key == "peak_heater":
            return Config.SHELLY_RELAY_CHANNEL_MAIN
        return Config.SHELLY_RELAY_CHANNEL_SECOND

    def apply_heater_state(self, key, device_id, target_state, device_name, slot_info=None):
        """Applies heater state through the configured control backend."""
        backend = self._heater_backend(key)
        if backend == "shelly":
            channel = self._heater_relay_channel(key)
            self.apply_shelly_relay_state(key, channel, target_state, device_name, slot_info)
            return

        self.apply_device_state(device_id, target_state, device_name, slot_info, key=key)

    def apply_shelly_relay_state(self, key, channel, target_state, device_name, slot_info=None):
        """Apply state to a Shelly relay with a renewable fail-safe lease."""
        current_state_str = self.system_state[key].get("state", "UNKNOWN")
        is_online = self.system_state[key].get("online", False)

        if not is_online:
            logger.warning(f"{device_name} Shelly relay status is not confirmed. Attempting control anyway...")

        # Reconcile the Shelly every control-loop pass.  ON renews the bounded
        # auto-OFF lease; OFF is also repeated so a manual/app change cannot
        # leave the immersion heater energized until the hourly health check.
        should_command = True
        if should_command:
            action = "Turning ON" if target_state else "Turning OFF"
            reason = f"Slot: {slot_info['value_inc_vat']}p until {slot_info['valid_to']}" if slot_info else "No active slot"
            if not target_state and self.cooldown_until:
                reason = "Thermostat hold active"

            logger.info(f"{action} {device_name} via Shelly relay channel {channel} ({reason})")

            if not self.dry_run:
                result = self.shelly.set_relay(
                    channel=channel,
                    turn_on=target_state,
                    toggle_after=Config.SHELLY_CONTROL_LEASE_SECONDS if target_state else None,
                )
                if isinstance(result, dict) and result.get("success"):
                    self.system_state[key]["online"] = True
                    self.system_state[key]["state"] = "ON" if target_state else "OFF"
                    self.system_state[key]["last_error"] = None
                else:
                    error_msg = result.get("error") if isinstance(result, dict) else result
                    # The cached ON value represents only the previous accepted
                    # command. Once a lease renewal fails it must not be used as
                    # proof that the relay is still energised; the bounded
                    # auto-OFF lease may already have expired.
                    self.system_state[key]["online"] = False
                    self.system_state[key]["state"] = "UNKNOWN"
                    self.system_state[key]["last_error"] = error_msg
                    logger.error(f"Shelly relay command for {device_name} did not succeed. Response: {result}")
                return

            logger.info("[DRY RUN] Command skipped.")

    def apply_device_state(self, device_id, target_state, device_name, slot_info=None, key=None):
        """Applies state to device if needed."""
        if not device_id:
            logger.warning(f"{device_name} has no Tuya device id configured; skipping control.")
            return

        if key is None:
            key = "peak_heater" if device_id == Config.TUYA_DEVICE_ID_MAIN else "off_peak_heater"
        
        # Pull from internal cache instead of polling Tuya API directly
        current_state_str = self.system_state[key].get("state", "UNKNOWN")
        is_online = self.system_state[key].get("online", False)
        
        # Convert "ON"/"OFF" string to boolean for comparison
        is_on = (current_state_str == "ON")
        
        if not is_online:
            logger.warning(f"⚠️ {device_name} reported OFFLINE in cache. Attempting control anyway...")
            # Do NOT return, try to send command
        
        if is_on != target_state or current_state_str == "UNKNOWN":
            action = "Turning ON" if target_state else "Turning OFF"
            reason = f"Slot: {slot_info['value_inc_vat']}p until {slot_info['valid_to']}" if slot_info else "No active slot"
            
            if not target_state and self.cooldown_until:
                reason = "Thermostat hold active"
                
            logger.info(f"{action} {device_name} ({reason})")
            
            if not self.dry_run:
                # Send the actual command
                result = None
                if target_state:
                    result = self.tuya.turn_on(device_id)
                else:
                    result = self.tuya.turn_off(device_id)

                if isinstance(result, dict) and result.get('success'):
                    self.system_state[key]["online"] = True
                    self.system_state[key]["state"] = "ON" if target_state else "OFF"
                    self.system_state[key]["last_error"] = None
                else:
                    if isinstance(result, dict):
                        error_msg = result.get('msg') or result.get('error') or result.get('raw') or result
                    else:
                        error_msg = result
                    self.system_state[key]["last_error"] = error_msg
                    logger.error(
                        f"Tuya command for {device_name} did not succeed. "
                        f"Keeping cached state as {current_state_str} so the controller retries. "
                        f"Response: {result}"
                    )
                return
            else:
                logger.info("[DRY RUN] Command skipped.")

    def perform_health_check(self):
        """Checks and prints the health status of all devices."""
        logger.info("--- PERFORMING DEVICE HEALTH CHECK ---")
        
        devices = [
            ("Peak Heater", Config.TUYA_DEVICE_ID_MAIN, "peak_heater"),
        ]

        if Config.STORAGE_HEATER_ENABLED or Config.OFF_PEAK_HEATER_TARGET == 'second':
            devices.append(("Off-Peak Heater", Config.TUYA_DEVICE_ID_SECOND, "off_peak_heater"))
        else:
            logger.info("Off-Peak/Storage Heater: skipped health check because off-peak slots are routed to main heater.")
            self.system_state["off_peak_heater"]["online"] = False
            self.system_state["off_peak_heater"]["state"] = "DISABLED"
            self.system_state["off_peak_heater"]["last_error"] = "Storage heater disabled by config; off-peak slots routed to main heater."

        for name, dev_id, key in devices:
            self._check_heater_health(name, dev_id, key)

        logger.info("--- HEALTH CHECK COMPLETE ---\n")

    def _check_heater_health(self, name, dev_id, key):
        backend = self._heater_backend(key)

        if backend == "shelly":
            channel = self._heater_relay_channel(key)
            status = self.shelly.get_relay_status(channel=channel)
            if not (status and status.get('success', False)):
                logger.error(f"Warning: {name}: SHELLY RELAY STATUS UNKNOWN. Response: {status}")
                self.system_state[key]["online"] = False
                self.system_state[key]["state"] = "UNKNOWN"
                self.system_state[key]["last_error"] = status.get('error') if isinstance(status, dict) else status
                return

            is_online = status.get('online', False)
            state = "ON" if status.get('is_on') else "OFF"
            self.system_state[key]["online"] = is_online
            self.system_state[key]["state"] = state
            self.system_state[key]["last_error"] = None if is_online else "Shelly relay status is invalid"
            logger.info(f"{name}: Shelly relay channel {channel} | State: {state}")
            return

        if not dev_id:
            logger.warning(f"{name} has no Tuya device id configured; skipping health check.")
            self.system_state[key]["online"] = False
            self.system_state[key]["state"] = "UNKNOWN"
            self.system_state[key]["last_error"] = "Tuya device id is not configured"
            return

        status = self.tuya.get_status(dev_id)
        if not (status and status.get('success', False)):
            logger.error(f"Warning: {name}: STATUS UNKNOWN. Response: {status}")
            self.system_state[key]["online"] = False
            self.system_state[key]["state"] = "UNKNOWN"
            if isinstance(status, dict):
                self.system_state[key]["last_error"] = status.get('msg') or status.get('error') or status
            else:
                self.system_state[key]["last_error"] = status
            return

        is_online = status.get('online', False)
        state = "ON" if status.get('is_on') else "OFF"
        self.system_state[key]["online"] = is_online
        self.system_state[key]["state"] = state

        if is_online:
            self.system_state[key]["last_error"] = None
            logger.info(f"{name}: ONLINE | State: {state}")
        else:
            message = f"{name} is offline in Tuya Cloud; commands will not switch the heater until the device is online."
            self.system_state[key]["last_error"] = message
            logger.error(message)

    def get_state(self):
        """Returns the current system state for UI."""
        return {
            "status": self.system_state,
            "schedule": {
                "main": self.main_heater_slots,
                "second": self.second_heater_slots
            }
        }

    def run(self):
        # 1. Verification on startup
        self.perform_health_check()
        self.update_schedule()

        # Health check every hour (keep this on fixed schedule)
        schedule.every(1).hours.do(self.perform_health_check)

        logger.info("Starting Control Loop (Press Ctrl+C to stop)")
        logger.info(f"Smart Scheduler Config: Budget={Config.DAILY_HEATING_BUDGET_HOURS}h, MaxPrice={Config.ABSOLUTE_MAX_PRICE}p, BelowAvg={Config.USE_BELOW_AVERAGE}")
        logger.info(f"Thermostat Control Mode: {self.thermostat_mode}")
        if self.thermostat_detector:
            logger.info(
                "Thermostat policy: on>=%sW off<=%sW arm=%sm/%.0fWh "
                "cooldown=%sm max_deferral=%sm",
                Config.THERMOSTAT_POWER_ON_THRESHOLD_W,
                Config.THERMOSTAT_POWER_OFF_THRESHOLD_W,
                Config.THERMOSTAT_MIN_REAL_HEAT_MINUTES,
                Config.THERMOSTAT_MIN_REAL_HEAT_WH,
                Config.THERMOSTAT_MIN_COOLDOWN_MINUTES,
                Config.THERMOSTAT_MAX_DEFERRAL_MINUTES,
            )
        logger.info(f"Storage Heater Enabled: {Config.STORAGE_HEATER_ENABLED}")
        logger.info(f"Off-Peak Heater Target: {Config.OFF_PEAK_HEATER_TARGET}")
        logger.info(f"Main Heater Control: {Config.MAIN_HEATER_CONTROL}")
        logger.info(f"Second Heater Control: {Config.SECOND_HEATER_CONTROL}")
        if Config.MAIN_HEATER_CONTROL == 'shelly' or Config.SECOND_HEATER_CONTROL == 'shelly':
            logger.info(f"Shelly ON lease: {Config.SHELLY_CONTROL_LEASE_SECONDS}s")
        if not Config.STORAGE_HEATER_ENABLED:
            logger.info("Storage heater is disabled by config.")
        if Config.OFF_PEAK_HEATER_TARGET == 'main':
            logger.info("Off-peak slots will use the main heater.")
        else:
            logger.info("Off-peak slots will use the lower/storage heater.")
        if Config.BLOCKED_HOURS:
            logger.info(f"Blocked hours: {Config.BLOCKED_HOURS}")

        try:
            while True:
                try:
                    schedule.run_pending()

                    # Smart schedule updates based on time of day
                    if self.should_update_schedule():
                        self.update_schedule()

                    self.control_loop()
                except Exception as e:
                    logger.error(f"CRITICAL ERROR in control loop: {e}", exc_info=True)
                    time.sleep(5)

                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Stopping...")

if __name__ == "__main__":
    if Config.DRY_RUN:
        logger.warning("Starting Service in DRY RUN mode. Heater commands will be logged but not sent.")
    else:
        logger.warning("Starting Service in LIVE mode. Heater commands are enabled.")
    controller = SmartWaterController(dry_run=Config.DRY_RUN)
    controller.run()
