import sys
import os

# Add ingestion directory to path so we can import modules
sys.path.append(os.path.join(os.getcwd(), 'ingestion'))

from ingestion.tuya_manager import TuyaManager
from ingestion.services.shelly_manager import ShellyManager
from ingestion.config import Config

def check_tuya():
    print("\n--- CHECKING TUYA ---", flush=True)
    try:
        tuya = TuyaManager()
        if not tuya.enabled:
            print("❌ Tuya Manager is DISABLED (Check config)", flush=True)
            return

        print(f"Tuya Initialized. Devices: Main={Config.TUYA_DEVICE_ID_MAIN}, Second={Config.TUYA_DEVICE_ID_SECOND}", flush=True)
        
        # Check Main (Peak Heater)
        if Config.TUYA_DEVICE_ID_MAIN:
            print(f"Querying Main Device ({Config.TUYA_DEVICE_ID_MAIN})...", flush=True)
            status = tuya.get_status(Config.TUYA_DEVICE_ID_MAIN)
            if status:
                print(f"✅ Main Device: Online={status['online']}, ON={status['is_on']}", flush=True)
            else:
                print("❌ Main Device: Failed to get status", flush=True)
        
        # Check Second (Off-Peak Heater)
        if Config.TUYA_DEVICE_ID_SECOND:
            print(f"Querying Second Device ({Config.TUYA_DEVICE_ID_SECOND})...", flush=True)
            status = tuya.get_status(Config.TUYA_DEVICE_ID_SECOND)
            if status:
                print(f"✅ Second Device: Online={status['online']}, ON={status['is_on']}", flush=True)
            else:
                print("❌ Second Device: Failed to get status", flush=True)

    except Exception as e:
        print(f"❌ Tuya Exception: {e}", flush=True)

def check_shelly():
    print("\n--- CHECKING SHELLY ---")
    try:
        shelly = ShellyManager()
        if not shelly.enabled:
            print("❌ Shelly Manager is DISABLED (Check config)")
            return
            
        print(f"Shelly Initialized. Server={Config.SHELLY_SERVER}, Device={Config.SHELLY_DEVICE_ID}")
        
        status = shelly.get_status()
        if status:
            print("✅ Shelly API Connection Successful")
            emeters = status.get('emeters', [])
            for idx, em in enumerate(emeters):
                print(f"   Channel {idx}: {em.get('power', 0)} W, {em.get('voltage', 0)} V")
        else:
            print("❌ Shelly Status Fetch Failed")

    except Exception as e:
        print(f"❌ Shelly Exception: {e}")

if __name__ == "__main__":
    print("Starting Diagnostics...")
    check_tuya()
    check_shelly()
    print("\nDiagnostics Complete.")
