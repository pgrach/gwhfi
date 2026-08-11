import os
import sys
import types
import unittest
from unittest.mock import patch

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv_stub

from config import Config, blocked_hours_env, bool_env, clamped_int_env


class DryRunConfigTests(unittest.TestCase):
    def test_missing_value_uses_safe_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(bool_env("DRY_RUN", True))

    def test_explicit_false_enables_live_mode(self):
        with patch.dict(os.environ, {"DRY_RUN": "false"}, clear=True):
            self.assertFalse(bool_env("DRY_RUN", True))

    def test_invalid_value_stays_in_safe_mode(self):
        with patch.dict(os.environ, {"DRY_RUN": "definitely"}, clear=True):
            self.assertTrue(bool_env("DRY_RUN", True))


class ShellySafetyConfigTests(unittest.TestCase):
    def test_control_lease_is_clamped_to_conservative_range(self):
        cases = (
            ({}, 180),
            ({"LEASE": "0"}, 120),
            ({"LEASE": "180"}, 180),
            ({"LEASE": "999"}, 300),
            ({"LEASE": "invalid"}, 180),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment):
                with patch.dict(os.environ, environment, clear=True):
                    self.assertEqual(
                        clamped_int_env("LEASE", 180, 120, 300),
                        expected,
                    )

    def test_single_shelly_relay_cannot_receive_both_heater_routes(self):
        with (
            patch.object(Config, "MAIN_HEATER_CONTROL", "shelly"),
            patch.object(Config, "SECOND_HEATER_CONTROL", "shelly"),
        ):
            self.assertFalse(Config.validate_shelly_control_routing())

        with (
            patch.object(Config, "MAIN_HEATER_CONTROL", "tuya"),
            patch.object(Config, "SECOND_HEATER_CONTROL", "shelly"),
        ):
            self.assertTrue(Config.validate_shelly_control_routing())


class BlockedHoursSafetyTests(unittest.TestCase):
    SAFE_HOURS = [7, 8, 16, 17, 18]

    def test_invalid_values_restore_safe_defaults(self):
        invalid_values = (
            "not-json",
            "{}",
            "7",
            '[7, "8"]',
            "[true]",
            "[-1]",
            "[24]",
        )
        for invalid_value in invalid_values:
            with self.subTest(value=invalid_value):
                with patch.dict(os.environ, {"BLOCKED_HOURS": invalid_value}, clear=True):
                    self.assertEqual(
                        blocked_hours_env("BLOCKED_HOURS", self.SAFE_HOURS),
                        self.SAFE_HOURS,
                    )

    def test_valid_hour_lists_are_preserved(self):
        with patch.dict(os.environ, {"BLOCKED_HOURS": "[0, 12, 23]"}, clear=True):
            self.assertEqual(
                blocked_hours_env("BLOCKED_HOURS", self.SAFE_HOURS),
                [0, 12, 23],
            )


if __name__ == "__main__":
    unittest.main()
