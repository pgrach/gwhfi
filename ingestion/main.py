import time
import logging
import schedule
from datetime import datetime, timedelta
from config import Config
from services.time_service import TimeService
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
        self.octopus = OctopusClient(Config.OCTOPUS_PRODUCT_CODE, Config.OCTOPUS_REGION_CODE)
        
        self.main_heater_slots = []
        self.second_heater_slots = []
        
        # State storage for UI
        self.system_state = {
            "peak_heater": {"online": False, "state": "UNKNOWN"},
            "off_peak_heater": {"online": False, "state": "UNKNOWN"},
            "last_updated": None,
            "next_schedule_update": None,
            "rates": []
        }
        
        # Verify clock on startup
        offset, safe = self.time_service.check_system_clock()
        if not safe:
            logger.error("System clock is unreliable! Aborting startup.")
            raise SystemExit("Unreliable system clock")

    def update_schedule(self):
        """Fetches rates and calculates heating slots."""
        logger.info("Updating schedule from Octopus Energy...")
        rates = self.octopus.get_rates()
        
        if not rates:
            logger.error("Failed to fetch rates. Retaining old schedule if exists.")
            return

        # Filter out past rates (keep only slots that end in the future)
        now = self.time_service.now()
        future_rates = [r for r in rates if r['valid_to'] > now]

        if not future_rates:
            logger.warning("No future rates found! Waiting for next update.")
            return

        # Off-Peak Heater: Smart Daily Analysis (Below Average)
        # cheapest = self.octopus.find_cheapest_blocks(future_rates, Config.MAIN_HEATER_DURATION_HOURS)
        # self.main_heater_slots = cheapest
        
        smart_daily = self.octopus.find_smart_daily_slots(future_rates)
        self.main_heater_slots = smart_daily
        
        # Peak Heater: Below threshold
        negative = self.octopus.get_negative_rates(future_rates, Config.SECOND_HEATER_THRESHOLD)
        self.second_heater_slots = negative
        
        # Update UI state
        self.system_state["rates"] = rates  # Store all rates for graph if needed
        self.system_state["next_schedule_update"] = (datetime.now() + timedelta(hours=6)).strftime("%H:%M")
        
        logger.info(f"Scheduled Peak Heater Slots: {len(self.second_heater_slots)}")
        for slot in self.second_heater_slots:
            logger.info(f"  Peak: {slot['valid_from']} - {slot['valid_to']} ({slot['value_inc_vat']}p)")

        logger.info(f"Scheduled Off-Peak Heater Slots: {len(self.main_heater_slots)}")
        for slot in self.main_heater_slots:
            logger.info(f"  Off-Peak: {slot['valid_from']} - {slot['valid_to']} ({slot['value_inc_vat']}p)")

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
        
        # 1. Peak Heater Control (Device MAIN, Negative Slots)
        active_peak, slot_peak = self.is_in_slot(self.second_heater_slots, now_utc)
        self.apply_device_state(Config.TUYA_DEVICE_ID_MAIN, active_peak, "Peak Heater", slot_peak)

        # 2. Off-Peak Heater Control (Device SECOND, Daily Slots)
        if Config.TUYA_DEVICE_ID_SECOND:
            active_offpeak, slot_offpeak = self.is_in_slot(self.main_heater_slots, now_utc)
            self.apply_device_state(Config.TUYA_DEVICE_ID_SECOND, active_offpeak, "Off-Peak Heater", slot_offpeak)
            
        # Update cached state explicitly for UI if apply_device_state didn't trigger health check type logic
        # Ideally, we rely on periodic perform_health_check for "Online" status, but here we know the "Target" state.
        # Let's trust perform_health_check for truth, but maybe update "Target" here?
        # For simplicity, we'll let perform_health_check handle the bulk of "State" truth.

    def apply_device_state(self, device_id, target_state, device_name, slot_info=None):
        """Applies state to device if needed."""
        status_info = self.tuya.get_status(device_id) 
        
        is_on = False
        is_online = False
        
        if status_info:
            is_on = status_info.get('is_on', False)
            is_online = status_info.get('online', False)
            
            # Update Internal State Cache
            key = "peak_heater" if device_id == Config.TUYA_DEVICE_ID_MAIN else "off_peak_heater"
            self.system_state[key]["online"] = is_online
            self.system_state[key]["state"] = "ON" if is_on else "OFF"
            
        if not is_online:
            logger.warning(f"⚠️ {device_name} is OFFLINE. Cannot control it.")
            return # Skip control if offline
        
        if is_on != target_state:
            action = "Turning ON" if target_state else "Turning OFF"
            reason = f"Slot: {slot_info['value_inc_vat']}p until {slot_info['valid_to']}" if slot_info else "No active slot"
            logger.info(f"{action} {device_name} ({reason})")
            
            if not self.dry_run:
                if target_state:
                    self.tuya.turn_on(device_id)
                    self.system_state[key]["state"] = "ON"
                else:
                    self.tuya.turn_off(device_id)
                    self.system_state[key]["state"] = "OFF"
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
            if status:
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
        # Enrich with schedule info
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
        
        # Schedule rate updates every 6 hours
        schedule.every(6).hours.do(self.update_schedule)
        
        # Schedule health check every hour
        schedule.every(1).hours.do(self.perform_health_check)
        
        logger.info("Starting Control Loop (Press Ctrl+C to stop)")
        try:
            while True:
                try:
                    schedule.run_pending()
                    self.control_loop()
                except Exception as e:
                    logger.error(f"CRITICAL ERROR in control loop: {e}", exc_info=True)
                    # Sleep a bit to avoid rapid-fire error loops
                    time.sleep(5)
                
                time.sleep(60) # Check every minute
        except KeyboardInterrupt:
            logger.info("Stopping...")

if __name__ == "__main__":
    # LIVE MODE
    logger.info("Starting Service in LIVE MODE...")
    controller = SmartWaterController(dry_run=False)
    controller.run()
