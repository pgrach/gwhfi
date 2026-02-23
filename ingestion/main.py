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
            "peak_heater": {"online": False, "state": "UNKNOWN"},
            "off_peak_heater": {"online": False, "state": "UNKNOWN"},
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

        # 1. Peak Heater Control (Device MAIN, Negative Slots)
        # Note: Peak heater ignores cooldown logic for now (it's free energy strategy)
        active_peak, slot_peak = self.is_in_slot(self.second_heater_slots, now_utc)
        self.apply_device_state(Config.TUYA_DEVICE_ID_MAIN, active_peak, "Peak Heater", slot_peak)

        # 2. Off-Peak Heater Control (Device SECOND, Windows)
        active_offpeak, slot_offpeak = self.is_in_slot(self.main_heater_slots, now_utc)
        
        # --- Smart Cooldown Logic ---
        if active_offpeak and self.cooldown_until:
             # We should be ON, but Cooldown is active -> FORCE OFF
             active_offpeak = False
             slot_offpeak = None # Clear slot info to avoid confusing logs
             # logger.debug("Skipping heating slot due to Cooldown.")
             
        elif active_offpeak and not self.cooldown_until:
            # We are ON. Check Power Consumption.
            # Using Channel 1 for Off-Peak Heater
            power = self.shelly.get_power(channel=1)

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

        self.apply_device_state(Config.TUYA_DEVICE_ID_SECOND, active_offpeak, "Off-Peak Heater", slot_offpeak)

    def apply_device_state(self, device_id, target_state, device_name, slot_info=None):
        """Applies state to device if needed."""
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
                    
                # Handle Tuya response explicitly
                if isinstance(result, dict) and result.get('quota_exceeded'):
                    logger.error(f"⚠️ TUYA API FAILURE: Quota is exhausted. Forcing {device_name} to remain ON as failsafe!")
                    self.system_state[key]["state"] = "ON"
                else:
                    # Assume success or normal failure, update cache to what we tried to set it to
                    self.system_state[key]["state"] = "ON" if target_state else "OFF"
            else:
                logger.info("[DRY RUN] Command skipped.")

    def perform_health_check(self):
        """Checks and prints the health status of all devices."""
        logger.info("--- PERFORMING DEVICE HEALTH CHECK ---")
        
        devices = [
            ("Peak Heater", Config.TUYA_DEVICE_ID_MAIN, "peak_heater"),
            ("Off-Peak Heater", Config.TUYA_DEVICE_ID_SECOND, "off_peak_heater")
        ]
        
        for name, dev_id, key in devices:
            if not dev_id: continue
            
            status = self.tuya.get_status(dev_id)
            if isinstance(status, dict) and status.get('quota_exceeded'):
                logger.error(f"⚠️ {name}: TUYA API QUOTA EXHAUSTED! Forcing State to ON.")
                self.system_state[key]["online"] = True
                self.system_state[key]["state"] = "ON"
            elif status and status.get('success', False):
                is_online = status.get('online', False)
                state = "ON" if status.get('is_on') else "OFF"
                
                # Update Cache
                self.system_state[key]["online"] = is_online
                self.system_state[key]["state"] = state
                
                if is_online:
                    logger.info(f"✅ {name}: ONLINE | State: {state}")
                else:
                    logger.warning(f"❌ {name}: OFFLINE | (Last State: {state})")
            else:
                logger.error(f"⚠️ {name}: STATUS UNKNOWN (Connection Error)")
                self.system_state[key]["online"] = False
                self.system_state[key]["state"] = "UNKNOWN"
        
        logger.info("--- HEALTH CHECK COMPLETE ---\n")
        
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
