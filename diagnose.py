import sys
import os
import time

# Add ingestion directory to path
sys.path.append(os.path.join(os.getcwd(), 'ingestion'))

from ingestion.tuya_manager import TuyaManager
from ingestion.services.shelly_manager import ShellyManager
from ingestion.config import Config

def check_devices():
    print("Starting Diagnostics...\n", flush=True)
    
    # --- TUYA CHECK ---
    print("--- CHECKING TUYA ---", flush=True)
    try:
        tuya = TuyaManager()
        if not tuya.enabled:
            print("❌ Tuya Manager is DISABLED.", flush=True)
        else:
            print(f"Device 1 (Main/Peak) ID: {Config.TUYA_DEVICE_ID_MAIN}", flush=True)
            status_main = tuya.get_status(Config.TUYA_DEVICE_ID_MAIN)
            if status_main:
                print(f"✅ STATUS: Online={status_main['online']}, Switch={status_main['is_on']}", flush=True)
            else:
                print("❌ STATUS: FAILED (Offline or Wrong ID)", flush=True)
            
            time.sleep(1) # Gentle delay
            
            print(f"\nDevice 2 (Off-Peak) ID: {Config.TUYA_DEVICE_ID_SECOND}", flush=True)
            status_second = tuya.get_status(Config.TUYA_DEVICE_ID_SECOND)
            if status_second:
                print(f"✅ STATUS: Online={status_second['online']}, Switch={status_second['is_on']}", flush=True)
            else:
                print("❌ STATUS: FAILED (Offline or Wrong ID)", flush=True)

    except Exception as e:
        print(f"❌ Exception in Tuya Check: {e}", flush=True)

    # --- SHELLY CHECK ---
    print("\n--- CHECKING SHELLY ---", flush=True)
    try:
        shelly = ShellyManager()
        if not shelly.enabled:
             print("❌ Shelly Manager is DISABLED.", flush=True)
        else:
             print("✅ Shelly Manager Initialized.", flush=True)
             # Basic power check
             p0 = shelly.get_power(0)
             p1 = shelly.get_power(1)
             print(f"Channel 0: {p0} W")
             print(f"Channel 1: {p1} W")
             
    except Exception as e:
        print(f"❌ Exception in Shelly Check: {e}", flush=True)

    print("\nDiagnostics Complete.", flush=True)

if __name__ == "__main__":
    check_devices()
