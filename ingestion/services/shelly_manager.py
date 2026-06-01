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

    def get_relay_status(self, channel=0):
        """Returns relay state for Shelly devices that expose relay outputs."""
        status = self.get_status()
        if not status:
            return {"success": False, "error": "Shelly status request failed"}

        relays = status.get("relays", [])
        if channel >= len(relays):
            return {
                "success": False,
                "error": f"Shelly relay channel {channel} is not available",
                "relay_count": len(relays),
            }

        relay = relays[channel]
        return {
            "success": True,
            "online": relay.get("is_valid", True),
            "is_on": relay.get("ison", False),
            "raw": relay,
        }

    def set_relay(self, channel=0, turn_on=True):
        """Switches a Shelly relay channel through Shelly Cloud."""
        if not self.enabled:
            return {"success": False, "error": "Shelly control disabled"}

        url = f"{self.server}/device/relay/control"
        payload = {
            "id": self.device_id,
            "auth_key": self.auth_key,
            "channel": channel,
            "turn": "on" if turn_on else "off",
        }

        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("isok"):
                logger.info(f"Shelly relay command succeeded for channel {channel} (State: {turn_on})")
                return {"success": True, "raw": data}

            logger.error(f"Shelly relay command failed for channel {channel}: {data}")
            return {"success": False, "error": data.get("errors") or data.get("error") or data}
        except Exception as e:
            logger.error(f"Failed to switch Shelly relay channel {channel}: {e}")
            return {"success": False, "error": str(e)}
