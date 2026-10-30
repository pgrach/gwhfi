import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import types

if "schedule" not in sys.modules:
    sys.modules["schedule"] = types.ModuleType("schedule")
if "ntplib" not in sys.modules:
    ntplib_stub = types.ModuleType("ntplib")
    ntplib_stub.NTPClient = Mock
    sys.modules["ntplib"] = ntplib_stub
if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv_stub
if "pytz" not in sys.modules:
    pytz_stub = types.ModuleType("pytz")
    pytz_stub.timezone = lambda _name: timezone.utc
    sys.modules["pytz"] = pytz_stub
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    requests_stub.get = Mock()
    requests_stub.post = Mock()
    requests_stub.delete = Mock()
    sys.modules["requests"] = requests_stub

from main import SmartWaterController


class ThermostatControllerIntegrationTests(unittest.TestCase):
    NOW = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)

    def make_controller(self, mode="shadow", *, relay_on=True, persistence_result=True):
        controller = SmartWaterController.__new__(SmartWaterController)
        controller.cooldown_until = None
        controller.thermostat_mode = mode
        controller.system_state = {
            "cooldown_mode": False,
            "cooldown_until": None,
            "off_peak_heater": {
                "online": relay_on,
                "state": "ON" if relay_on else "OFF",
                "last_error": None,
            },
            "thermostat_control": {
                "mode": mode,
                "state": "HEATING",
                "suppressed": False,
                "reason": None,
                "hold_until": None,
                "evidence": {},
            },
        }
        controller.shelly = Mock()
        controller.shelly.get_meter_reading.return_value = {
            "power_w": 0.0,
            "energy_total_wh": 12_345.0,
        }
        controller.thermostat_detector = Mock()
        controller.thermostat_detector.state = "HEATING"
        controller.thermostat_detector.hold_until = None
        controller.thermostat_detector.export_state.return_value = {
            "version": 1,
            "state": "HEATING",
        }
        controller.thermostat_state_storage = Mock()
        controller.thermostat_state_storage.save_transition.return_value = persistence_result
        return controller

    def hold_decision(self):
        return SimpleNamespace(
            state="HOLD",
            suppress=True,
            reason="consecutive_low_power",
            event="tank_satisfied",
            hold_until=self.NOW + timedelta(hours=2),
            evidence={"armed": True},
        )

    def test_shadow_decision_never_changes_scheduled_request(self):
        controller = self.make_controller(mode="shadow")
        controller.thermostat_detector.observe.return_value = self.hold_decision()
        slot = {"valid_from": self.NOW, "valid_to": self.NOW + timedelta(minutes=30)}

        active, returned_slot = controller.apply_thermostat_policy(True, slot, self.NOW)

        self.assertTrue(active)
        self.assertIs(returned_slot, slot)
        self.assertFalse(controller.system_state["thermostat_control"]["suppressed"])

    def test_live_persisted_hold_suppresses_scheduled_request(self):
        controller = self.make_controller(mode="live", persistence_result=True)
        controller.thermostat_detector.observe.return_value = self.hold_decision()
        slot = {"valid_from": self.NOW, "valid_to": self.NOW + timedelta(minutes=30)}

        active, returned_slot = controller.apply_thermostat_policy(True, slot, self.NOW)

        self.assertFalse(active)
        self.assertIsNone(returned_slot)
        self.assertTrue(controller.system_state["thermostat_control"]["suppressed"])

    def test_live_persistence_failure_restores_state_and_fails_open(self):
        controller = self.make_controller(mode="live", persistence_result=False)
        controller.thermostat_detector.observe.return_value = self.hold_decision()
        slot = {"valid_from": self.NOW, "valid_to": self.NOW + timedelta(minutes=30)}

        active, returned_slot = controller.apply_thermostat_policy(True, slot, self.NOW)

        self.assertTrue(active)
        self.assertIs(returned_slot, slot)
        controller.thermostat_detector.restore_state.assert_called_once_with({
            "version": 1,
            "state": "HEATING",
        })
        self.assertFalse(controller.system_state["thermostat_control"]["suppressed"])

    def test_detector_exception_fails_open(self):
        controller = self.make_controller(mode="live")
        controller.thermostat_detector.observe.side_effect = RuntimeError("bad sample")
        slot = {"valid_from": self.NOW, "valid_to": self.NOW + timedelta(minutes=30)}

        active, returned_slot = controller.apply_thermostat_policy(True, slot, self.NOW)

        self.assertTrue(active)
        self.assertIs(returned_slot, slot)

    def test_unconfirmed_relay_is_not_interpreted_as_thermostat_off(self):
        controller = self.make_controller(mode="live", relay_on=False)
        controller.thermostat_detector.state = "PROBE"
        controller.thermostat_detector.observe.return_value = SimpleNamespace(
            state="PROBE",
            suppress=False,
            reason="relay_not_commanded_on",
            event=None,
            hold_until=None,
            evidence={},
        )

        active, _ = controller.apply_thermostat_policy(True, {}, self.NOW)

        self.assertTrue(active)
        controller.shelly.get_meter_reading.assert_not_called()
        self.assertFalse(
            controller.thermostat_detector.observe.call_args.kwargs["relay_commanded_on"]
        )

    def test_failed_lease_renewal_invalidates_cached_relay_on_state(self):
        controller = self.make_controller(mode="live", relay_on=True)
        controller.dry_run = False
        controller.shelly.set_relay.return_value = {
            "success": False,
            "error": "cloud timeout",
        }

        controller.apply_shelly_relay_state(
            "off_peak_heater",
            0,
            True,
            "Off-Peak Heater",
            {"value_inc_vat": 12.0, "valid_to": self.NOW + timedelta(minutes=30)},
        )

        relay = controller.system_state["off_peak_heater"]
        self.assertFalse(relay["online"])
        self.assertEqual(relay["state"], "UNKNOWN")
        self.assertEqual(relay["last_error"], "cloud timeout")


if __name__ == "__main__":
    unittest.main()
