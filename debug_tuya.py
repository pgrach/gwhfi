import tinytuya
import logging
import json
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_tuya_direct():
    print("Connecting to Tuya Cloud...")
    cloud = tinytuya.Cloud(
        apiRegion=Config.TUYA_REGION, 
        apiKey=Config.TUYA_ACCESS_ID, 
        apiSecret=Config.TUYA_ACCESS_KEY, 
        apiDeviceID=Config.TUYA_DEVICE_ID_MAIN
    )

    main_id = Config.TUYA_DEVICE_ID_MAIN
    second_id = Config.TUYA_DEVICE_ID_SECOND
    
    ids_to_check = [main_id, second_id]
    
    for device_id in ids_to_check:
        if not device_id: continue
        
        print(f"\n--- Checking Device ID: {device_id} ---")
        
        # Method 1: Get Device Details (should contain 'online')
        # URL: /v1.0/devices/{device_id}
        try:
            print(f"Requesting /v1.0/devices/{device_id} ...")
            result = cloud.cloudrequest(f'/v1.0/devices/{device_id}')
            
            if result and 'result' in result:
                data = result['result']
                name = data.get('name', 'Unknown')
                online = data.get('online', 'Unknown')
                print(f"  Name: {name}")
                print(f"  ONLINE Status: {online}")
                print(f"  Result: {json.dumps(result, indent=2)}")
            else:
                print(f"  Failed: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    debug_tuya_direct()
