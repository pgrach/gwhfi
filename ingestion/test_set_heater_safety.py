import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv_stub

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    requests_stub.Session = Mock
    sys.modules["requests"] = requests_stub

if "tuya_manager" not in sys.modules:
    tuya_manager_stub = types.ModuleType("tuya_manager")
    tuya_manager_stub.TuyaManager = Mock
    sys.modules["tuya_manager"] = tuya_manager_stub

import set_heater


class ManualHeaterSafetyTests(unittest.TestCase):
    def test_dry_run_skips_shelly_manager_entirely(self):
        args = SimpleNamespace(heater="shelly-second", state="on")
        with (
            patch.object(set_heater, "parse_args", return_value=args),
            patch.object(set_heater.Config, "DRY_RUN", True),
            patch.object(set_heater, "ShellyManager") as manager_factory,
        ):
            self.assertEqual(set_heater.main(), 0)

        manager_factory.assert_not_called()

    def test_live_shelly_on_uses_bounded_control_lease(self):
        args = SimpleNamespace(heater="shelly-second", state="on")
        manager = Mock()
        manager.set_relay.return_value = {"success": True}
        with (
            patch.object(set_heater, "parse_args", return_value=args),
            patch.object(set_heater.Config, "DRY_RUN", False),
            patch.object(set_heater.Config, "SHELLY_RELAY_CHANNEL_SECOND", 0),
            patch.object(set_heater.Config, "SHELLY_CONTROL_LEASE_SECONDS", 180),
            patch.object(set_heater, "ShellyManager", return_value=manager),
        ):
            self.assertEqual(set_heater.main(), 0)

        manager.set_relay.assert_called_once_with(
            channel=0,
            turn_on=True,
            toggle_after=180,
        )

    def test_live_shelly_off_is_explicit_without_flip_back(self):
        args = SimpleNamespace(heater="shelly-second", state="off")
        manager = Mock()
        manager.set_relay.return_value = {"success": True}
        with (
            patch.object(set_heater, "parse_args", return_value=args),
            patch.object(set_heater.Config, "DRY_RUN", False),
            patch.object(set_heater.Config, "SHELLY_RELAY_CHANNEL_SECOND", 0),
            patch.object(set_heater, "ShellyManager", return_value=manager),
        ):
            self.assertEqual(set_heater.main(), 0)

        manager.set_relay.assert_called_once_with(
            channel=0,
            turn_on=False,
            toggle_after=None,
        )


if __name__ == "__main__":
    unittest.main()
