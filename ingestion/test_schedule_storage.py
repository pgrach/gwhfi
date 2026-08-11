import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.ModuleType("requests")

from services import schedule_storage


class ScheduleStorageReplacementTests(unittest.TestCase):
    def make_storage(self):
        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "secret"},
        ):
            return schedule_storage.ScheduleStorage()

    def test_zero_slot_replacement_succeeds_only_after_successful_delete(self):
        replace_from = datetime(2026, 8, 11, tzinfo=timezone.utc)
        replace_to = replace_from + timedelta(days=1)

        for status_code, expected in ((204, True), (500, False)):
            with self.subTest(status_code=status_code):
                storage = self.make_storage()
                response = types.SimpleNamespace(status_code=status_code, text="delete result")
                with (
                    patch.object(schedule_storage.requests, "delete", return_value=response, create=True) as delete_mock,
                    patch.object(schedule_storage.requests, "post", create=True) as post_mock,
                ):
                    result = storage.save_schedule(
                        [],
                        heater_type="off_peak",
                        replace_from=replace_from,
                        replace_to=replace_to,
                    )

                self.assertEqual(result, expected)
                delete_mock.assert_called_once()
                post_mock.assert_not_called()

    def test_failed_delete_returns_false_without_posting_replacement_slots(self):
        storage = self.make_storage()
        slot_start = datetime(2026, 8, 11, 1, tzinfo=timezone.utc)
        slots = [{
            "valid_from": slot_start,
            "valid_to": slot_start + timedelta(minutes=30),
            "value_inc_vat": 4.2,
        }]
        response = types.SimpleNamespace(status_code=503, text="unavailable")

        with (
            patch.object(schedule_storage.requests, "delete", return_value=response, create=True),
            patch.object(schedule_storage.requests, "post", create=True) as post_mock,
        ):
            result = storage.save_schedule(slots, heater_type="off_peak")

        self.assertFalse(result)
        post_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
