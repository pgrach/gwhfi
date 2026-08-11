import requests
import logging
import threading
import time
from config import Config

logger = logging.getLogger(__name__)

class ShellyManager:
    CLOUD_MIN_REQUEST_INTERVAL_SECONDS = 1.05

    def __init__(self, session=None, monotonic=None, sleeper=None):
        self.server = (Config.SHELLY_SERVER or "").rstrip('/')
        if self.server and not self.server.startswith(("http://", "https://")):
            self.server = f"https://{self.server}"
        self.auth_key = Config.SHELLY_AUTH_KEY
        self.meter_device_id = Config.SHELLY_METER_DEVICE_ID
        self.relay_device_id = Config.SHELLY_RELAY_DEVICE_ID
        self.session = session or requests.Session()
        self._monotonic = monotonic or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._request_lock = threading.Lock()
        self._last_request_at = None

        self.monitoring_enabled = bool(self.server and self.auth_key and self.meter_device_id)
        self.control_enabled = bool(self.server and self.auth_key and self.relay_device_id)
        self.enabled = self.monitoring_enabled or self.control_enabled

        if not self.monitoring_enabled:
            logger.warning("Shelly meter configuration missing. Power monitoring disabled.")
        if not self.control_enabled:
            logger.warning("Shelly relay configuration missing. Relay control disabled.")

    def _post(self, url, **kwargs):
        """Issue one Cloud API request while respecting the account rate limit."""
        with self._request_lock:
            if self._last_request_at is not None:
                elapsed = self._monotonic() - self._last_request_at
                wait_seconds = self.CLOUD_MIN_REQUEST_INTERVAL_SECONDS - elapsed
                if wait_seconds > 0:
                    self._sleeper(wait_seconds)

            try:
                return self.session.post(url, **kwargs)
            finally:
                # Failed requests still count toward the service's request rate.
                self._last_request_at = self._monotonic()

    def _get_device(self, device_id):
        """Fetch one device through Shelly Cloud Control API v2."""
        if not all([self.server, self.auth_key, device_id]):
            return None

        url = f"{self.server}/v2/devices/api/get"
        try:
            response = self._post(
                url,
                params={"auth_key": self.auth_key},
                json={"ids": [device_id], "select": ["status"]},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and data:
                return data[0]
            logger.error("Shelly Cloud returned no device data for the requested device.")
        except requests.RequestException as exc:
            # Do not log the prepared URL: it contains the cloud authorization key.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.error("Shelly Cloud status request failed (HTTP %s).", status or "unavailable")
        except (TypeError, ValueError):
            logger.error("Shelly Cloud returned an invalid status response.")
        return None

    def get_status(self, device_id=None):
        """Return the status object for a Shelly Cloud device."""
        device_id = device_id or self.meter_device_id
        if not device_id:
            return None

        device = self._get_device(device_id)
        if not device or not bool(device.get("online")):
            return None
        return device.get("status") or {}

    def get_power(self, channel=0):
        """Returns the current power (W) for the specified channel."""
        status = self.get_status(self.meter_device_id)
        if not status:
            return None

        emeters = status.get("emeters", [])
        if channel < len(emeters):
            return emeters[channel].get("power", 0.0)

        # Gen2 energy-meter component shapes.
        for component, field in (
            (f"em:{channel}", "total_act_power"),
            (f"em1:{channel}", "act_power"),
            (f"switch:{channel}", "apower"),
        ):
            value = status.get(component, {}).get(field)
            if value is not None:
                return value

        return None

    def get_relay_status(self, channel=0):
        """Returns relay state for Shelly devices that expose relay outputs."""
        if not self.control_enabled:
            return {"success": False, "error": "Shelly relay control is not configured"}

        status = self.get_status(self.relay_device_id)
        if not status:
            return {"success": False, "error": "Shelly status request failed"}

        switch = status.get(f"switch:{channel}")
        if switch is not None:
            if not isinstance(switch, dict):
                return {
                    "success": False,
                    "error": f"Shelly relay channel {channel} returned an invalid status object",
                    "raw": switch,
                }
            output = switch.get("output")
            if type(output) is not bool:
                return {
                    "success": False,
                    "error": f"Shelly relay channel {channel} returned an invalid output state",
                    "raw": switch,
                }
            return {
                "success": True,
                "online": True,
                "is_on": output,
                "raw": switch,
            }

        # Backwards-compatible Gen1 response parsing.
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

    def set_relay(self, channel=0, turn_on=True, toggle_after=None):
        """Switch a Shelly relay through Cloud API v2.

        ON commands should include a short toggle_after lease. The controller
        renews that lease every minute; if it stops, the device turns itself off.
        """
        if not self.control_enabled:
            return {"success": False, "error": "Shelly control disabled"}

        lease_seconds = None
        if turn_on:
            if isinstance(toggle_after, bool):
                return {"success": False, "error": "Shelly ON requires a bounded auto-OFF lease"}
            try:
                lease_seconds = int(toggle_after)
            except (TypeError, ValueError, OverflowError):
                return {"success": False, "error": "Shelly ON requires a bounded auto-OFF lease"}

            if not (
                Config.SHELLY_CONTROL_LEASE_MIN_SECONDS
                <= lease_seconds
                <= Config.SHELLY_CONTROL_LEASE_MAX_SECONDS
            ):
                return {
                    "success": False,
                    "error": (
                        "Shelly ON lease must be between "
                        f"{Config.SHELLY_CONTROL_LEASE_MIN_SECONDS} and "
                        f"{Config.SHELLY_CONTROL_LEASE_MAX_SECONDS} seconds"
                    ),
                }

        url = f"{self.server}/v2/devices/api/set/switch"
        payload = {
            "id": self.relay_device_id,
            "channel": channel,
            "on": bool(turn_on),
        }
        if turn_on:
            payload["toggle_after"] = lease_seconds

        try:
            response = self._post(
                url,
                params={"auth_key": self.auth_key},
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info(
                "Shelly relay command accepted for channel %s (state=%s, lease=%s).",
                channel,
                "ON" if turn_on else "OFF",
                payload.get("toggle_after"),
            )
            return {"success": True}
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.error(
                "Shelly relay command failed for channel %s (HTTP %s).",
                channel,
                status or "unavailable",
            )
            return {"success": False, "error": f"Shelly Cloud HTTP {status or 'unavailable'}"}
        except (TypeError, ValueError):
            logger.error("Shelly Cloud returned an invalid relay-control response.")
            return {"success": False, "error": "Invalid Shelly Cloud response"}
