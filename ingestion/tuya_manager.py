import tinytuya
import logging
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TuyaManager:
    def __init__(self):
        self.enabled = False
        if not Config.validate():
            logger.warning("Tuya Configuration missing. Control logic will be DISABLED.")
            return

        try:
            self.cloud = tinytuya.Cloud(
                apiRegion=Config.TUYA_REGION, 
                apiKey=Config.TUYA_ACCESS_ID, 
                apiSecret=Config.TUYA_ACCESS_KEY, 
                apiDeviceID=Config.TUYA_DEVICE_ID_MAIN
            )
            self.enabled = True
        except Exception as e:
            logger.error(f"Failed to initialize Tuya Cloud: {e}")
            self.enabled = False

    def get_status(self, device_id):
        """
        Gets the full device status including online/offline state.
        Returns a dict with 'online' (bool) and 'switch_1' (bool).
        """
        if not self.enabled:
            return None

        try:
            # Use cloudrequest to get full device details including 'online' status
            result = self.cloud.cloudrequest(f'/v1.0/devices/{device_id}')
            if result and 'result' in result:
                data = result['result']
                online = data.get('online', False)
                status_list = data.get('status', [])
                
                switch_state = False
                for item in status_list:
                    if item.get('code') == 'switch_1':
                        switch_state = item.get('value')
                        break
                        
                return {
                    'online': online,
                    'is_on': switch_state,
                    'raw': data
                }
            return None
        except Exception as e:
            logger.error(f"Error getting status for device {device_id}: {e}")
            return None

    def turn_on(self, device_id):
        return self._send_command(device_id, True)

    def turn_off(self, device_id):
        return self._send_command(device_id, False)

    def _send_command(self, device_id, switch_state):
        if not self.enabled:
            logger.debug(f"Control disabled. Skipping command to {device_id}")
            return None

        try:
            # Standard Tuya switch command
            commands = {
                "commands": [
                    {"code": "switch_1", "value": switch_state}
                ]
            }
            result = self.cloud.sendcommand(device_id, commands)
            logger.info(f"Command result for {device_id} (State: {switch_state}): {result}")
            return result
        except Exception as e:
            logger.error(f"Error sending command to {device_id}: {e}")
            return None

if __name__ == "__main__":
    print("Initializing Tuya Manager...")
    try:
        manager = TuyaManager()
        
        main_id = Config.TUYA_DEVICE_ID_MAIN
        second_id = Config.TUYA_DEVICE_ID_SECOND
        
        print(f"\nChecking Main Device ({main_id})...")
        status_main = manager.get_status(main_id)
        if status_main:
            print(f"Main Device Status: Online={status_main['online']}, Switch={status_main['is_on']}")
        else:
            print("Main Device Status: Failed to fetch")
        
        if second_id:
            print(f"\nChecking Second Device ({second_id})...")
            status_second = manager.get_status(second_id)
            if status_second:
                print(f"Second Device Status: Online={status_second['online']}, Switch={status_second['is_on']}")
            else:
                print("Second Device Status: Failed to fetch")
            
    except ValueError as e:
        print(f"Configuration Warning: {e} (Running in headless/monitoring mode)")
    except Exception as e:
        print(f"Unexpected Error: {e}")
