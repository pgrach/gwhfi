import logging
from config import Config

try:
    import tinytuya
except ImportError:
    tinytuya = None


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


TUYA_ACCOUNT_ERROR_CODES = {
    28841001: "No cloud development plan subscribed",
    28841002: "Cloud development plan expired",
    28841003: "Cloud development plan bill overdue",
    28841004: "Trial Edition quota exhausted",
    28841101: "API is not subscribed",
    28841102: "API subscription expired",
    28841103: "API bill overdue",
    28841104: "API quota exhausted",
    28841105: "Project is not authorized to use this API",
    28841106: "API is not subscribed",
}


class TuyaManager:
    def __init__(self):
        self.enabled = False
        self.cloud_enabled = False
        self.local_enabled = False
        self.local_devices = {}
        self.last_error = None
        self.control_mode = Config.TUYA_CONTROL_MODE

        if self.control_mode not in {'cloud', 'local', 'local_then_cloud'}:
            logger.warning(f"Unknown TUYA_CONTROL_MODE={self.control_mode}. Falling back to cloud.")
            self.control_mode = 'cloud'

        if tinytuya is None:
            logger.error("TinyTuya is not installed. Tuya control logic will be DISABLED.")
            return

        wants_cloud = self.control_mode in {'cloud', 'local_then_cloud'}
        wants_local = self.control_mode in {'local', 'local_then_cloud'}

        if wants_local:
            self.local_enabled = self._has_any_local_config()
            if not self.local_enabled:
                logger.warning("Local Tuya control requested but local keys are missing.")

        if wants_cloud and Config.validate_cloud():
            try:
                self.cloud = tinytuya.Cloud(
                    apiRegion=Config.TUYA_REGION,
                    apiKey=Config.TUYA_ACCESS_ID,
                    apiSecret=Config.TUYA_ACCESS_KEY,
                    apiDeviceID=Config.TUYA_DEVICE_ID_MAIN
                )
                self.cloud_enabled = True
            except Exception as e:
                logger.error(f"Failed to initialize Tuya Cloud: {e}")
                self.cloud_enabled = False
        elif wants_cloud:
            logger.warning("Tuya cloud configuration missing. Cloud control will be disabled.")

        self.enabled = self.cloud_enabled or self.local_enabled

    def get_status(self, device_id):
        """
        Gets full device status including online/offline state.
        Returns a dict with 'online' (bool) and 'is_on' (bool).
        """
        if self.control_mode in {'local', 'local_then_cloud'} and self.has_local_config(device_id):
            local_result = self.get_local_status(device_id)
            if local_result.get('success') or self.control_mode == 'local':
                return local_result

            logger.warning(f"Local Tuya status failed for {device_id}; trying cloud fallback.")

        if not self.cloud_enabled:
            return {'success': False, 'error': 'Tuya cloud control disabled'}

        try:
            result = self.cloud.cloudrequest(f'/v1.0/devices/{device_id}')

            if isinstance(result, dict) and result.get('success') is False:
                self.last_error = self._failure_response(result, "status fetch", device_id)
                return self.last_error

            if result and isinstance(result.get('result'), dict):
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
                    'raw': data,
                    'success': True
                }

            self.last_error = self._failure_response(result, "status fetch", device_id)
            return self.last_error
        except Exception as e:
            logger.error(f"Error getting status for device {device_id}: {e}")
            self.last_error = {'success': False, 'error': str(e)}
            return self.last_error

    def turn_on(self, device_id):
        return self._send_command(device_id, True)

    def turn_off(self, device_id):
        return self._send_command(device_id, False)

    def _send_command(self, device_id, switch_state):
        if self.control_mode in {'local', 'local_then_cloud'} and self.has_local_config(device_id):
            local_result = self._send_local_command(device_id, switch_state)
            if local_result.get('success') or self.control_mode == 'local':
                return local_result

            logger.warning(f"Local Tuya command failed for {device_id}; trying cloud fallback.")

        if not self.cloud_enabled:
            logger.debug(f"Cloud control disabled. Skipping cloud command to {device_id}")
            return {'success': False, 'error': 'Tuya cloud control disabled'}

        commands = {
            "commands": [
                {"code": "switch_1", "value": switch_state}
            ]
        }

        try:
            command_path = self._command_path(device_id)
            try:
                result = self.cloud.cloudrequest(
                    command_path,
                    action="POST",
                    post=commands
                )
            except TypeError:
                # Older TinyTuya versions expose the same endpoint via sendcommand.
                result = self.cloud.sendcommand(device_id, commands, command_path)

            if self._success_response(result):
                logger.info(f"Tuya command succeeded for {device_id} (State: {switch_state}): {result}")
                return {'success': True, 'raw': result}

            self.last_error = self._failure_response(result, "command", device_id)
            return self.last_error
        except Exception as e:
            logger.error(f"Error sending command to {device_id}: {e}")
            self.last_error = {'success': False, 'error': str(e)}
            return self.last_error

    def _command_path(self, device_id):
        return f"/v1.0/iot-03/devices/{device_id}/commands"

    def get_local_status(self, device_id):
        if not self.has_local_config(device_id):
            return {'success': False, 'error': 'Local Tuya config missing'}

        try:
            device = self._get_local_device(device_id)
            result = device.status()
            if self._local_success_response(result):
                switch_state = self._local_switch_state(result, self._local_config(device_id)['dps'])
                return {
                    'online': True,
                    'is_on': switch_state,
                    'raw': result,
                    'success': True,
                    'source': 'local'
                }

            self.last_error = self._local_failure_response(result, "local status fetch", device_id)
            return self.last_error
        except Exception as e:
            logger.error(f"Error getting local status for device {device_id}: {e}")
            self.last_error = {'success': False, 'error': str(e), 'source': 'local'}
            return self.last_error

    def has_local_config(self, device_id):
        cfg = self._local_config(device_id)
        return bool(cfg and cfg['device_id'] and cfg['local_key'])

    def _has_any_local_config(self):
        return (
            self.has_local_config(Config.TUYA_DEVICE_ID_MAIN)
            or self.has_local_config(Config.TUYA_DEVICE_ID_SECOND)
        )

    def _local_config(self, device_id):
        if device_id == Config.TUYA_DEVICE_ID_MAIN:
            return {
                'device_id': Config.TUYA_DEVICE_ID_MAIN,
                'address': Config.TUYA_DEVICE_IP_MAIN,
                'local_key': Config.TUYA_LOCAL_KEY_MAIN,
                'version': Config.TUYA_PROTOCOL_VERSION_MAIN,
                'dps': Config.TUYA_LOCAL_DPS_MAIN,
            }

        if device_id == Config.TUYA_DEVICE_ID_SECOND:
            return {
                'device_id': Config.TUYA_DEVICE_ID_SECOND,
                'address': Config.TUYA_DEVICE_IP_SECOND,
                'local_key': Config.TUYA_LOCAL_KEY_SECOND,
                'version': Config.TUYA_PROTOCOL_VERSION_SECOND,
                'dps': Config.TUYA_LOCAL_DPS_SECOND,
            }

        return None

    def _get_local_device(self, device_id):
        if device_id in self.local_devices:
            return self.local_devices[device_id]

        cfg = self._local_config(device_id)
        device = tinytuya.OutletDevice(
            dev_id=cfg['device_id'],
            address=cfg['address'],
            local_key=cfg['local_key'],
            version=cfg['version']
        )
        device.set_socketTimeout(5)
        self.local_devices[device_id] = device
        return device

    def _send_local_command(self, device_id, switch_state):
        if not self.has_local_config(device_id):
            return {'success': False, 'error': 'Local Tuya config missing'}

        try:
            cfg = self._local_config(device_id)
            device = self._get_local_device(device_id)
            if switch_state:
                result = device.turn_on(switch=cfg['dps'])
            else:
                result = device.turn_off(switch=cfg['dps'])

            if self._local_success_response(result):
                logger.info(f"Local Tuya command succeeded for {device_id} (State: {switch_state}): {result}")
                return {'success': True, 'raw': result, 'source': 'local'}

            self.last_error = self._local_failure_response(result, "local command", device_id)
            return self.last_error
        except Exception as e:
            logger.error(f"Error sending local command to {device_id}: {e}")
            self.last_error = {'success': False, 'error': str(e), 'source': 'local'}
            return self.last_error

    def _local_switch_state(self, result, dps):
        dps_map = result.get('dps', {}) if isinstance(result, dict) else {}
        value = dps_map.get(str(dps), dps_map.get(dps, False))
        return bool(value)

    def _local_success_response(self, result):
        if not isinstance(result, dict):
            return False

        if result.get('success') is False:
            return False

        error_value = result.get('Error') or result.get('Err') or result.get('error')
        if error_value:
            return False

        return True

    def _local_failure_response(self, result, operation, device_id):
        msg = result.get('Error') or result.get('Err') or result.get('error') if isinstance(result, dict) else str(result)
        logger.error(f"Tuya {operation} failed for {device_id}: {msg}. Raw response: {result}")
        return {
            'success': False,
            'msg': msg,
            'source': 'local',
            'raw': result
        }

    def _success_response(self, result):
        if not isinstance(result, dict):
            return False

        if result.get('success') is False:
            return False

        if result.get('result') is False:
            return False

        return result.get('success') is True or result.get('result') is True

    def _failure_response(self, result, operation, device_id):
        code = self._account_error(result)
        msg = result.get('msg') if isinstance(result, dict) else str(result)
        if not msg and isinstance(result, dict) and result.get('success') is True and result.get('result') is False:
            msg = "Tuya accepted the request but returned result=false; the device is likely offline or unable to execute the command"
        error_name = TUYA_ACCOUNT_ERROR_CODES.get(code)

        if code:
            logger.error(
                f"TUYA ACCOUNT/API FAILURE during {operation} for {device_id}: "
                f"{code} ({error_name}). Raw response: {result}"
            )
        else:
            logger.error(
                f"Tuya {operation} failed for {device_id}: {msg}. "
                f"Raw response: {result}"
            )

        return {
            'success': False,
            'code': code,
            'msg': msg,
            'account_error': code is not None,
            'quota_exceeded': code in {28841004, 28841104},
            'raw': result
        }

    def _account_error(self, result):
        if not isinstance(result, dict):
            return None

        code = result.get('code')
        if code is None:
            return None

        try:
            code = int(code)
        except (TypeError, ValueError):
            return None

        if code in TUYA_ACCOUNT_ERROR_CODES:
            return code

        return None


if __name__ == "__main__":
    print("Initializing Tuya Manager...")
    try:
        manager = TuyaManager()

        main_id = Config.TUYA_DEVICE_ID_MAIN
        second_id = Config.TUYA_DEVICE_ID_SECOND

        print(f"\nChecking Main Device ({main_id})...")
        status_main = manager.get_status(main_id)
        if status_main and status_main.get('success'):
            print(f"Main Device Status: Online={status_main['online']}, Switch={status_main['is_on']}")
        else:
            print(f"Main Device Status: Failed to fetch ({status_main})")

        if second_id:
            print(f"\nChecking Second Device ({second_id})...")
            status_second = manager.get_status(second_id)
            if status_second and status_second.get('success'):
                print(f"Second Device Status: Online={status_second['online']}, Switch={status_second['is_on']}")
            else:
                print(f"Second Device Status: Failed to fetch ({status_second})")

    except ValueError as e:
        print(f"Configuration Warning: {e} (Running in headless/monitoring mode)")
    except Exception as e:
        print(f"Unexpected Error: {e}")
