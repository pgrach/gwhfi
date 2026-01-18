import requests
import logging
from config import Config

logger = logging.getLogger(__name__)

class ShellyManager:
    def __init__(self):
        self.server = Config.SHELLY_SERVER
        self.auth_key = Config.SHELLY_AUTH_KEY
        self.device_id = Config.SHELLY_DEVICE_ID
        
        if not all([self.server, self.auth_key, self.device_id]):
            logger.warning("Shelly Configuration missing. Power monitoring disabled.")
            self.enabled = False
        else:
            self.enabled = True

    def get_status(self):
        """Fetches device status from Shelly Cloud API."""
        if not self.enabled:
            return None
            
        url = f"{self.server}/device/status"
        payload = {
            "id": self.device_id,
            "auth_key": self.auth_key
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("isok"):
                return data.get("data", {}).get("device_status", {})
            else:
                logger.error(f"Shelly API Error: {data}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch Shelly status: {e}")
            return None

    def get_power(self, channel=0):
        """Returns the current power (W) for the specified channel."""
        status = self.get_status()
        if not status:
            return None
            
        emeters = status.get("emeters", [])
        if channel < len(emeters):
            return emeters[channel].get("power", 0.0)
        
        return None
