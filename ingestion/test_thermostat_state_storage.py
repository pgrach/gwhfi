import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    sys.modules["requests"] = requests_stub

from services.thermostat_state_storage import ThermostatStateStorage


class ThermostatStateStorageTests(unittest.TestCase):
    def make_storage(self):
        environment = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "secret",
        }
        env_patch = patch.dict(os.environ, environment, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        return ThermostatStateStorage(site_id="home", heater_key="off_peak")

    def test_load_returns_only_versioned_payload(self):
        storage = self.make_storage()
        response = Mock()
        response.json.return_value = [{
            "state_payload": {"version": 1, "state": "HOLD"},
            "shadow_mode": False,
        }]

        with patch(
            "services.thermostat_state_storage.requests.get",
            return_value=response,
            create=True,
        ) as get:
            self.assertEqual(storage.load_state(live_only=True), {"version": 1, "state": "HOLD"})

        response.raise_for_status.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"]["site_id"], "eq.home")

    def test_live_startup_ignores_shadow_state(self):
        storage = self.make_storage()
        response = Mock()
        response.json.return_value = [{
            "state_payload": {"version": 1, "state": "HOLD"},
            "shadow_mode": True,
        }]

        with patch(
            "services.thermostat_state_storage.requests.get",
            return_value=response,
            create=True,
        ):
            self.assertIsNone(storage.load_state(live_only=True))

    def test_transition_maps_detector_states_to_schema_modes(self):
        storage = self.make_storage()
        responses = [Mock(), Mock()]
        now = datetime(2026, 10, 30, 20, 20, tzinfo=timezone.utc)
        payload = {
            "version": 1,
            "state": "HOLD",
            "hold_until": (now + timedelta(hours=2)).isoformat(),
            "tank_satisfied_at": now.isoformat(),
            "heating_started_at": (now - timedelta(hours=1)).isoformat(),
            "session_energy_wh": 3000,
        }

        with patch(
            "services.thermostat_state_storage.requests.post",
            side_effect=responses,
            create=True,
        ) as post:
            saved = storage.save_transition(
                occurred_at=now,
                state_payload=payload,
                mode_before="HEATING",
                mode_after="HOLD",
                event_type="tank_satisfied",
                shadow_mode=True,
                relay_commanded_on=True,
                power_w=0,
                energy_total_wh=123456,
                evidence={"reason": "consecutive_low_power"},
                policy_version=1,
                slot={
                    "valid_from": now - timedelta(minutes=20),
                    "valid_to": now + timedelta(minutes=10),
                },
            )

        self.assertTrue(saved)
        event_row = post.call_args_list[0].kwargs["json"]
        state_row = post.call_args_list[1].kwargs["json"]
        self.assertEqual(state_row["mode"], "holding")
        self.assertEqual(event_row["mode_before"], "heating")
        self.assertEqual(event_row["mode_after"], "holding")
        self.assertTrue(event_row["shadow_mode"])
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
