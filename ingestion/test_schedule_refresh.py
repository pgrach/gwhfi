import sys
import types
import unittest
from datetime import date, datetime, timedelta, timezone, tzinfo
from unittest.mock import Mock, patch


class LondonTestTimezone(tzinfo):
    """Small test-only London zone covering these August/October fixtures."""

    @staticmethod
    def _offset(value):
        if value is not None and 4 <= value.month <= 9:
            return timedelta(hours=1)
        return timedelta(0)

    def localize(self, value):
        return value.replace(tzinfo=self)

    def utcoffset(self, value):
        return self._offset(value)

    def dst(self, value):
        return self._offset(value)

    def tzname(self, value):
        return "BST" if self._offset(value) else "GMT"

    def fromutc(self, value):
        local = value.replace(tzinfo=None) + self._offset(value)
        return local.replace(tzinfo=self)


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
    pytz_stub.timezone = lambda _name: LondonTestTimezone()
    sys.modules["pytz"] = pytz_stub
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    requests_stub.get = Mock()
    requests_stub.post = Mock()
    requests_stub.delete = Mock()
    requests_stub.Session = Mock
    sys.modules["requests"] = requests_stub

from main import Config, SmartWaterController


def rate(start, price=20.0):
    return {
        "valid_from": start,
        "valid_to": start + timedelta(minutes=30),
        "value_inc_vat": price,
    }


def stored_rate(start, price=20.0):
    return {
        "id": 100,
        "slot_start": start.isoformat(),
        "slot_end": (start + timedelta(minutes=30)).isoformat(),
        "price": price,
        "heater_type": "off_peak",
        "computed_at": "2026-10-30T18:00:00+00:00",
    }


class SameDayScheduleRefreshTests(unittest.TestCase):
    """Protect the published daily plan from periodic-refresh budget resets."""

    NOW = datetime(2026, 10, 31, 6, 5, tzinfo=timezone.utc)
    TODAY = date(2026, 10, 31)
    TOMORROW = date(2026, 11, 1)

    def make_controller(self, persisted_today):
        controller = SmartWaterController.__new__(SmartWaterController)
        controller.time_service = Mock()
        controller.time_service.now.return_value = self.NOW
        controller.time_service.get_local_time.return_value = self.NOW
        controller.time_service.timezone = LondonTestTimezone()

        controller.octopus = Mock()
        controller.octopus.get_rates.return_value = [
            rate(self.NOW + timedelta(hours=1), 40.0),
            rate(datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc), 10.0),
        ]
        controller.octopus.get_negative_rates.return_value = []

        tomorrow_slot = rate(
            datetime(2026, 11, 1, 1, 30, tzinfo=timezone.utc), 12.0
        )
        controller.scheduler = Mock()
        controller.scheduler.tomorrow_scheduled = False
        controller.scheduler.has_tomorrow_rates.return_value = True
        controller.scheduler.compute_schedule_for_date.return_value = [tomorrow_slot]
        controller.scheduler.get_schedule_for_display.return_value = {"slots": []}

        controller.schedule_storage = Mock()
        controller.schedule_storage.enabled = True
        controller.schedule_storage.get_schedule.return_value = persisted_today
        controller.schedule_storage.save_schedule.return_value = True

        controller.main_heater_slots = []
        controller.second_heater_slots = []
        controller.system_state = {"rates": []}
        return controller, tomorrow_slot

    def test_refresh_reuses_persisted_today_plan_instead_of_minting_new_budget(self):
        overnight_start = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        controller, tomorrow_slot = self.make_controller(
            [stored_rate(overnight_start, 35.73)]
        )

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        compute_calls = controller.scheduler.compute_schedule_for_date.call_args_list
        self.assertEqual(len(compute_calls), 1)
        self.assertEqual(compute_calls[0].kwargs["target_date"], self.TOMORROW)

        today_slots = [
            slot
            for slot in controller.main_heater_slots
            if slot["valid_from"].date() == self.TODAY
        ]
        self.assertEqual(len(today_slots), 1)
        self.assertEqual(today_slots[0]["valid_from"], overnight_start)
        self.assertEqual(today_slots[0]["value_inc_vat"], 35.73)
        self.assertIn(tomorrow_slot, controller.main_heater_slots)

    def test_refresh_never_replaces_or_deletes_elapsed_today_rows(self):
        overnight_start = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        controller, tomorrow_slot = self.make_controller(
            [stored_rate(overnight_start, 35.73)]
        )

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        off_peak_saves = [
            call
            for call in controller.schedule_storage.save_schedule.call_args_list
            if call.kwargs["heater_type"] == "off_peak"
        ]
        self.assertEqual(len(off_peak_saves), 1)
        save = off_peak_saves[0]
        self.assertEqual(save.args[0], [tomorrow_slot])
        self.assertGreaterEqual(
            save.kwargs["replace_from"],
            datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            save.kwargs["replace_to"],
            datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc),
        )

    def test_repeated_refreshes_keep_the_same_published_today_plan(self):
        overnight_start = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        persisted = [stored_rate(overnight_start, 35.73)]
        controller, _ = self.make_controller(persisted)

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()
            controller.update_schedule()

        target_dates = [
            call.kwargs["target_date"]
            for call in controller.scheduler.compute_schedule_for_date.call_args_list
        ]
        self.assertEqual(target_dates, [self.TOMORROW, self.TOMORROW])
        today_slots = [
            slot
            for slot in controller.main_heater_slots
            if slot["valid_from"].date() == self.TODAY
        ]
        self.assertEqual([slot["valid_from"] for slot in today_slots], [overnight_start])

    def test_schedule_read_failure_falls_back_to_in_memory_today_plan(self):
        overnight_start = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        in_memory_slot = rate(overnight_start, 35.73)
        controller, _ = self.make_controller(None)
        controller.main_heater_slots = [in_memory_slot]

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        target_dates = [
            call.kwargs["target_date"]
            for call in controller.scheduler.compute_schedule_for_date.call_args_list
        ]
        self.assertEqual(target_dates, [])
        self.assertIn(in_memory_slot, controller.main_heater_slots)

    def test_schedule_read_failure_on_cold_start_fails_closed(self):
        controller, _ = self.make_controller(None)

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        controller.scheduler.compute_schedule_for_date.assert_not_called()
        controller.schedule_storage.save_schedule.assert_not_called()
        self.assertEqual(controller.main_heater_slots, [])

    def test_successful_empty_read_repairs_an_in_memory_today_plan(self):
        active_start = self.NOW - timedelta(minutes=5)
        in_memory_slot = rate(active_start, 35.73)
        controller, _ = self.make_controller([])
        controller.main_heater_slots = [in_memory_slot]
        controller.scheduler.has_tomorrow_rates.return_value = False

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        off_peak_saves = [
            call
            for call in controller.schedule_storage.save_schedule.call_args_list
            if call.kwargs["heater_type"] == "off_peak"
        ]
        self.assertEqual(len(off_peak_saves), 1)
        self.assertEqual(off_peak_saves[0].args[0], [in_memory_slot])
        is_active, active_slot = controller.is_in_slot(
            controller.main_heater_slots, self.NOW
        )
        self.assertTrue(is_active)
        self.assertEqual(active_slot, in_memory_slot)

    def test_missing_tomorrow_rates_preserve_published_tomorrow_plan(self):
        today_start = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        tomorrow_start = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
        controller, _ = self.make_controller([
            stored_rate(today_start, 35.73),
            stored_rate(tomorrow_start, 12.34),
        ])
        controller.scheduler.has_tomorrow_rates.return_value = False

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        controller.scheduler.compute_schedule_for_date.assert_not_called()
        off_peak_saves = [
            call
            for call in controller.schedule_storage.save_schedule.call_args_list
            if call.kwargs["heater_type"] == "off_peak"
        ]
        self.assertEqual(off_peak_saves, [])
        self.assertIn(tomorrow_start, {
            slot["valid_from"] for slot in controller.main_heater_slots
        })

    def test_unpersisted_new_today_plan_is_not_activated(self):
        controller, tomorrow_candidate = self.make_controller([])
        today_candidate = rate(self.NOW + timedelta(hours=1), 40.0)

        def compute_for_date(**kwargs):
            if kwargs["target_date"] == self.TODAY:
                return [today_candidate]
            return [tomorrow_candidate]

        controller.scheduler.compute_schedule_for_date.side_effect = compute_for_date
        controller.schedule_storage.save_schedule.side_effect = [False, True, True]

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        self.assertNotIn(today_candidate, controller.main_heater_slots)
        self.assertIn(tomorrow_candidate, controller.main_heater_slots)

    def test_failed_tomorrow_replacement_keeps_published_tomorrow_plan(self):
        today_start = datetime(2026, 10, 31, 1, 30, tzinfo=timezone.utc)
        published_tomorrow_start = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
        controller, tomorrow_candidate = self.make_controller([
            stored_rate(today_start, 35.73),
            stored_rate(published_tomorrow_start, 12.34),
        ])
        controller.schedule_storage.save_schedule.side_effect = [False, True]

        with patch.multiple(
            Config,
            DAILY_HEATING_BUDGET_HOURS=5.0,
            ABSOLUTE_MAX_PRICE=30.0,
            USE_BELOW_AVERAGE=True,
            BLOCKED_HOURS=[],
            SECOND_HEATER_THRESHOLD=0.0,
        ):
            controller.update_schedule()

        active_starts = {slot["valid_from"] for slot in controller.main_heater_slots}
        self.assertIn(published_tomorrow_start, active_starts)
        self.assertNotIn(tomorrow_candidate["valid_from"], active_starts)


if __name__ == "__main__":
    unittest.main()
