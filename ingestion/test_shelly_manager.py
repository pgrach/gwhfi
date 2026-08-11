import sys
import types
import unittest
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

from config import Config
from services.shelly_manager import ShellyManager


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class ShellyManagerTests(unittest.TestCase):
    def make_manager(self, response, monotonic=None, sleeper=None):
        session = Mock()
        session.post.return_value = response
        patches = (
            patch.object(Config, "SHELLY_SERVER", "https://example.shelly.cloud"),
            patch.object(Config, "SHELLY_AUTH_KEY", "secret"),
            patch.object(Config, "SHELLY_METER_DEVICE_ID", "meter-id"),
            patch.object(Config, "SHELLY_RELAY_DEVICE_ID", "relay-id"),
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        return ShellyManager(
            session=session,
            monotonic=monotonic,
            sleeper=sleeper,
        ), session

    def test_reads_gen2_relay_status(self):
        manager, _ = self.make_manager(FakeResponse([{
            "id": "relay-id",
            "online": 1,
            "status": {"switch:0": {"id": 0, "output": False}},
        }]))

        self.assertEqual(
            manager.get_relay_status(0),
            {
                "success": True,
                "online": True,
                "is_on": False,
                "raw": {"id": 0, "output": False},
            },
        )

    def test_on_command_uses_v2_api_and_fail_safe_lease(self):
        manager, session = self.make_manager(FakeResponse())

        result = manager.set_relay(channel=0, turn_on=True, toggle_after=180)

        self.assertTrue(result["success"])
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["params"], {"auth_key": "secret"})
        self.assertEqual(kwargs["json"], {
            "id": "relay-id",
            "channel": 0,
            "on": True,
            "toggle_after": 180,
        })

    def test_on_command_rejects_missing_or_out_of_range_lease(self):
        manager, session = self.make_manager(FakeResponse())

        for unsafe_lease in (None, True, 0, 119, 301):
            with self.subTest(toggle_after=unsafe_lease):
                session.post.reset_mock()
                result = manager.set_relay(
                    channel=0,
                    turn_on=True,
                    toggle_after=unsafe_lease,
                )
                self.assertFalse(result["success"])
                session.post.assert_not_called()

    def test_off_command_has_no_flip_back_timer(self):
        manager, session = self.make_manager(FakeResponse())

        result = manager.set_relay(channel=0, turn_on=False, toggle_after=180)

        self.assertTrue(result["success"])
        _, kwargs = session.post.call_args
        self.assertNotIn("toggle_after", kwargs["json"])

    def test_rejects_gen2_switch_status_without_boolean_output(self):
        for invalid_output in (None, 0, 1, "false"):
            with self.subTest(output=invalid_output):
                manager, _ = self.make_manager(FakeResponse([{
                    "id": "relay-id",
                    "online": 1,
                    "status": {"switch:0": {"id": 0, "output": invalid_output}},
                }]))

                result = manager.get_relay_status(0)
                self.assertFalse(result["success"])

    def test_rejects_malformed_gen2_switch_component(self):
        manager, _ = self.make_manager(FakeResponse([{
            "id": "relay-id",
            "online": 1,
            "status": {"switch:0": "not-an-object"},
        }]))

        self.assertFalse(manager.get_relay_status(0)["success"])

    def test_rate_limits_status_and_control_requests_together(self):
        now = [100.0]
        sleeps = []

        def monotonic():
            return now[0]

        def sleeper(seconds):
            sleeps.append(seconds)
            now[0] += seconds

        manager, session = self.make_manager(
            FakeResponse([{
                "id": "relay-id",
                "online": 1,
                "status": {"switch:0": {"id": 0, "output": False}},
            }]),
            monotonic=monotonic,
            sleeper=sleeper,
        )

        self.assertTrue(manager.get_relay_status(0)["success"])
        session.post.return_value = FakeResponse()
        self.assertTrue(manager.set_relay(channel=0, turn_on=False)["success"])

        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(
            sleeps[0],
            ShellyManager.CLOUD_MIN_REQUEST_INTERVAL_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
