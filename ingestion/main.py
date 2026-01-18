import time
import logging
import schedule
from datetime import datetime, timedelta
from config import Config
from services.time_service import TimeService
from services.shelly_manager import ShellyManager
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
        
        self.main_heater_slots = []
        self.second_heater_slots = []
        
        self.cooldown_until = None
        
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

    def _get_window_slots(self, rates, start_hour, end_hour, hours_needed):
        """
        Finds the cheapest slots within a specific daily window.
        start_hour: int (0-23)
        end_hour: int (0-23)
        """
        # Filter rates for the target window
        window_rates = []
        for r in rates:
            # We need to handle windows that cross midnight if needed (not needed for current spec)
            # Current spec: 00-07, 12-16, 19-23
            
            # Check if rate falls within window
            # We need to be careful with "valid_from" being today vs tomorrow
            # Simplification: Just check the hour component of valid_from
            h = r['valid_from'].hour
            if start_hour <= h < end_hour:
                window_rates.append(r)
                
        if not window_rates:
            return []
            
        return self.octopus.find_cheapest_blocks(window_rates, hours_needed)

    def update_schedule(self):
        """Fetches rates and calculates heating slots based on 3-Window Strategy."""
        logger.info("Updating schedule from Octopus Energy...")
        rates = self.octopus.get_rates()
        
        if not rates:
            logger.error("Failed to fetch rates. Retaining old schedule if exists.")
            return

        # Filter out past rates
        now = self.time_service.now()
        future_rates = [r for r in rates if r['valid_to'] > now]

        if not future_rates:
            logger.warning("No future rates found! Waiting for next update.")
            return
            
        # --- 3-WINDOW STRATEGY ---
        # 1. Night (00:00 - 07:00): 2 Hours
        night_slots = self._get_window_slots(future_rates, 0, 7, 2.0)
        
        # 2. Afternoon (12:00 - 16:00): 1 Hour
        afternoon_slots = self._get_window_slots(future_rates, 12, 16, 1.0)
        
        # 3. Evening (19:00 - 23:59): 1 Hour (Recovery)
        evening_slots = self._get_window_slots(future_rates, 19, 24, 1.0)
        
        # Combine
        self.main_heater_slots = night_slots + afternoon_slots + evening_slots
        self.main_heater_slots.sort(key=lambda x: x['valid_from']) # Keep sorted
        
        # Peak Heater: Standard Negative Logic
        negative = self.octopus.get_negative_rates(future_rates, Config.SECOND_HEATER_THRESHOLD)
        self.second_heater_slots = negative
        
        # Update UI state
        self.system_state["rates"] = rates
        self.system_state["next_schedule_update"] = (datetime.now() + timedelta(hours=6)).strftime("%H:%M")
        
        logger.info(f"--- Updated Schedule ({len(self.main_heater_slots)} slots) ---")
        for slot in self.main_heater_slots:
            logger.info(f"  [Off-Peak] {slot['valid_from'].strftime('%H:%M')} - {slot['valid_to'].strftime('%H:%M')} ({slot['value_inc_vat']}p)")

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
            # Using Channel 1 for Off-Peak Heater (implied from context)
            power = self.shelly.get_power(channel=1) 
            
            if power is not None:
                # Threshold: 10W (to be safe even if standby is 1-2W)
                if power < 10: 
                    logger.info(f"📉 Tank Full Detected (Power: {power}W). Triggering Smart Cooldown.")
                    # Set 90 minute cooldown
                    self.cooldown_until = now_utc + timedelta(minutes=90)
                    active_offpeak = False # Turn off immediately
                else:
                    # Log occasionally?
                    pass
            else:
                logger.warning("Failed to read power. Cannot verify Tank Full status.")

        self.apply_device_state(Config.TUYA_DEVICE_ID_SECOND, active_offpeak, "Off-Peak Heater", slot_offpeak)

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
            
            if not target_state and self.cooldown_until:
                reason = "Smart Cooldown Active"
                
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
        
        schedule.every(6).hours.do(self.update_schedule)
        schedule.every(1).hours.do(self.perform_health_check)
        
        logger.info("Starting Control Loop (Press Ctrl+C to stop)")
        try:
            while True:
                try:
                    schedule.run_pending()
                    self.control_loop()
                except Exception as e:
                    logger.error(f"CRITICAL ERROR in control loop: {e}", exc_info=True)
                    time.sleep(5)
                
                time.sleep(60) # Check every minute
        except KeyboardInterrupt:
            logger.info("Stopping...")

if __name__ == "__main__":
    # LIVE MODE
    logger.info("Starting Service in LIVE MODE...")
    controller = SmartWaterController(dry_run=False)
    controller.run()
