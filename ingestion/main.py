import time
import logging
import schedule
from datetime import datetime, timedelta
from config import Config
from services.time_service import TimeService
from services.shelly_manager import ShellyManager
from services.smart_scheduler import SmartScheduler
from services.schedule_storage import ScheduleStorage
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
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        logger.info(f"Initializing Smart Water Controller (Dry Run: {self.dry_run})")
        
        self.time_service = TimeService()
        
        self.tuya = TuyaManager()
        if not getattr(self.tuya, 'enabled', True):
            logger.warning("Tuya Manager disabled due to missing config.")
            
        self.shelly = ShellyManager()
        if not self.shelly.enabled:
            logger.warning("Shelly Manager disabled. Smart Cooldown will NOT function.")
        
        self.octopus = OctopusClient(Config.OCTOPUS_PRODUCT_CODE, Config.OCTOPUS_REGION_CODE)
        self.scheduler = SmartScheduler(Config)
        self.schedule_storage = ScheduleStorage()

        self.main_heater_slots = []
        self.second_heater_slots = []
        
        self.cooldown_until = None

        # Tank Full detection - require consecutive low readings to prevent false triggers
        self.low_power_count = 0
        self.LOW_POWER_THRESHOLD = 10  # Watts
        self.LOW_POWER_READINGS_REQUIRED = 3  # Need 3 consecutive readings (~3 mins)

        # State storage for UI
        self.system_state = {
            "peak_heater": {"online": False, "state": "UNKNOWN", "last_error": None},
            "off_peak_heater": {"online": False, "state": "UNKNOWN", "last_error": None},
            "cooldown_mode": False,
            "cooldown_until": None,
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
        today = now.date()
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
            blocked_hours=Config.BLOCKED_HOURS
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

        # Save schedule to Supabase for frontend visualization
        self.schedule_storage.save_schedule(self.main_heater_slots, heater_type="off_peak")
        self.schedule_storage.save_schedule(self.second_heater_slots, heater_type="peak")

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
        
        # Updates for UI
        self.system_state["cooldown_mode"] = False
        if self.cooldown_until:
            if now_utc < self.cooldown_until:
                self.system_state["cooldown_mode"] = True
                self.system_state["cooldown_until"] = self.cooldown_until.isoformat()
            else:
                # Cooldown expired
                logger.info("ℹ️ Smart Cooldown Expired. Resuming normal operation.")
                self.cooldown_until = None
                self.system_state["cooldown_until"] = None

        # 1. Work out which schedule windows are active.
        active_peak, slot_peak = self.is_in_slot(self.second_heater_slots, now_utc)
        active_offpeak, slot_offpeak = self.is_in_slot(self.main_heater_slots, now_utc)

        # 2. Smart Cooldown Logic for off-peak/storage schedule.
        if (
            active_offpeak
            and self.cooldown_until
            and Config.SMART_COOLDOWN_ENABLED
        ):
            # We should be ON, but Cooldown is active -> FORCE OFF
            active_offpeak = False
            slot_offpeak = None # Clear slot info to avoid confusing logs
            # logger.debug("Skipping heating slot due to Cooldown.")

        elif active_offpeak and not self.cooldown_until:
            # We are ON. Check Power Consumption.
            # Using Channel 1 for Off-Peak Heater
            if not Config.SMART_COOLDOWN_ENABLED:
                self.low_power_count = 0
            else:
                power = self.shelly.get_power(channel=Config.SHELLY_CHANNEL_SECOND)

                if power is not None:
                    # Check for Mechanical Timer Grace Period
                    # If the previous hour was blocked, the mechanical timer might be slow to close.
                    # Allow a 30-minute buffer where we ignore 0W readings.
                    prev_hour = (now_utc.hour - 1) % 24
                    is_grace_period = (prev_hour in Config.BLOCKED_HOURS) and (now_utc.minute < 30)

                    if is_grace_period and power < self.LOW_POWER_THRESHOLD:
                        logger.info(f"⏳ Grace Period (Mechanical Switch Lag): Ignoring low power ({power}W).")
                        self.low_power_count = 0
                    elif power < self.LOW_POWER_THRESHOLD:
                        self.low_power_count += 1
                        logger.debug(f"Low power reading {self.low_power_count}/{self.LOW_POWER_READINGS_REQUIRED} ({power}W)")

                        if self.low_power_count >= self.LOW_POWER_READINGS_REQUIRED:
                            # Confirmed tank is full after multiple consecutive low readings
                            logger.info(f"📉 Tank Full Confirmed ({self.low_power_count} consecutive readings < {self.LOW_POWER_THRESHOLD}W). Triggering Smart Cooldown.")
                            self.cooldown_until = now_utc + timedelta(minutes=90)
                            active_offpeak = False
                            self.low_power_count = 0  # Reset counter
                    else:
                        # Power is normal (heater actively drawing), reset counter
                        if self.low_power_count > 0:
                            logger.debug(f"Power restored ({power}W). Resetting low power counter.")
                        self.low_power_count = 0
                else:
                    logger.warning("Failed to read power. Cannot verify Tank Full status.")

        # 3. Apply controls. Heater 2 is usually physically switched off in this home.
        # In that one-heater setup, route off-peak scheduled slots to the main heater.
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
                self.system_state["off_peak_heater"]["last_error"] = "Storage heater physically switched off; off-peak slots routed to main heater."
        else:
            # Peak heater ignores cooldown logic because it is the free/negative-price strategy.
            self.apply_heater_state("peak_heater", Config.TUYA_DEVICE_ID_MAIN, active_peak, "Peak Heater", slot_peak)
            self.apply_heater_state("off_peak_heater", Config.TUYA_DEVICE_ID_SECOND, active_offpeak, "Off-Peak Heater", slot_offpeak)

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
        """Applies state to a Shelly relay channel if needed."""
        current_state_str = self.system_state[key].get("state", "UNKNOWN")
        is_online = self.system_state[key].get("online", False)
        is_on = current_state_str == "ON"

        if not is_online:
            logger.warning(f"{device_name} Shelly relay status is not confirmed. Attempting control anyway...")

        if is_on != target_state or current_state_str == "UNKNOWN":
            action = "Turning ON" if target_state else "Turning OFF"
            reason = f"Slot: {slot_info['value_inc_vat']}p until {slot_info['valid_to']}" if slot_info else "No active slot"
            if not target_state and self.cooldown_until:
                reason = "Smart Cooldown Active"

            logger.info(f"{action} {device_name} via Shelly relay channel {channel} ({reason})")

            if not self.dry_run:
                result = self.shelly.set_relay(channel=channel, turn_on=target_state)
                if isinstance(result, dict) and result.get("success"):
                    self.system_state[key]["online"] = True
                    self.system_state[key]["state"] = "ON" if target_state else "OFF"
                    self.system_state[key]["last_error"] = None
                else:
                    error_msg = result.get("error") if isinstance(result, dict) else result
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
                reason = "Smart Cooldown Active"
                
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
            logger.info("Off-Peak/Storage Heater: skipped health check because it is configured as physically switched off.")
            self.system_state["off_peak_heater"]["online"] = False
            self.system_state["off_peak_heater"]["state"] = "DISABLED"
            self.system_state["off_peak_heater"]["last_error"] = "Storage heater physically switched off; off-peak slots routed to main heater."

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
        logger.info(f"Smart Cooldown Enabled: {Config.SMART_COOLDOWN_ENABLED}")
        logger.info(f"Storage Heater Enabled: {Config.STORAGE_HEATER_ENABLED}")
        logger.info(f"Off-Peak Heater Target: {Config.OFF_PEAK_HEATER_TARGET}")
        logger.info(f"Main Heater Control: {Config.MAIN_HEATER_CONTROL}")
        logger.info(f"Second Heater Control: {Config.SECOND_HEATER_CONTROL}")
        if not Config.STORAGE_HEATER_ENABLED:
            logger.info("Storage heater is configured as physically switched off; off-peak slots will use the main heater.")
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
    # LIVE MODE
    logger.info("Starting Service in LIVE MODE...")
    controller = SmartWaterController(dry_run=False)
    controller.run()
