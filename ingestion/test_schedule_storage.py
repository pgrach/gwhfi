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

    def test_schedule_read_failure_is_distinct_from_successful_empty_result(self):
        storage = self.make_storage()
        failure = types.SimpleNamespace(status_code=503, json=lambda: [])
        success = types.SimpleNamespace(status_code=200, json=lambda: [])

        with patch.object(
            schedule_storage.requests,
            "get",
            side_effect=[failure, success],
            create=True,
        ):
            failed_rows = storage.get_schedule(heater_type="off_peak")
            empty_rows = storage.get_schedule(heater_type="off_peak")

        self.assertIsNone(failed_rows)
        self.assertEqual(empty_rows, [])

    def test_schedule_read_uses_encoded_request_params_for_utc_boundaries(self):
        storage = self.make_storage()
        response = types.SimpleNamespace(status_code=200, json=lambda: [])
        start = datetime(2026, 10, 31, tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        with patch.object(
            schedule_storage.requests,
            "get",
            return_value=response,
            create=True,
        ) as get_mock:
            storage.get_schedule(
                heater_type="off_peak",
                from_time=start,
                to_time=end,
            )

        request = get_mock.call_args
        self.assertEqual(request.args[0], "https://example.supabase.co/rest/v1/heating_schedule")
        self.assertEqual(request.kwargs["params"]["heater_type"], "eq.off_peak")
        self.assertEqual(
            request.kwargs["params"]["slot_start"],
            "gte.2026-10-31T00:00:00+00:00",
        )
        self.assertEqual(
            request.kwargs["params"]["slot_end"],
            "lte.2026-11-01T00:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
