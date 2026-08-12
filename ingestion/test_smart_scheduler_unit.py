import sys
import types
import unittest
from datetime import date, datetime, timedelta, timezone

try:
    import pytz  # noqa: F401
except ModuleNotFoundError:
    pytz_stub = types.ModuleType("pytz")
    # These fixtures are all in August, when Europe/London is UTC+1.
    # Production installs pytz from requirements.txt; this lightweight
    # fallback keeps the isolated unit test independent of host tzdata.
    pytz_stub.timezone = lambda _name: timezone(timedelta(hours=1))
    sys.modules["pytz"] = pytz_stub

from services.smart_scheduler import SmartScheduler


class SchedulerConfig:
    LOCAL_TIMEZONE = "Europe/London"


def rate(iso_start, price=10.0):
    start = datetime.fromisoformat(iso_start).replace(tzinfo=timezone.utc)
    return {
        "valid_from": start,
        "valid_to": start + timedelta(minutes=30),
        "value_inc_vat": price,
    }


class SmartSchedulerTimezoneTests(unittest.TestCase):
    def test_blocked_hours_are_interpreted_in_london_time_during_bst(self):
        scheduler = SmartScheduler(SchedulerConfig)
        allowed = rate("2026-08-11T14:30:00")  # 15:30 Europe/London
        blocked = rate("2026-08-11T15:00:00")  # 16:00 Europe/London

        selected = scheduler.compute_schedule_for_date(
            target_date=date(2026, 8, 11),
            rates=[allowed, blocked],
            budget_hours=0.5,
            max_price=30.0,
            use_below_average=True,
            blocked_hours=[16, 17, 18],
        )

        self.assertIn(allowed, selected)
        self.assertNotIn(blocked, selected)

    def test_rate_date_is_interpreted_in_london_time(self):
        scheduler = SmartScheduler(SchedulerConfig)
        after_midnight_local = rate("2026-08-10T23:30:00")  # 00:30 BST on Aug 11

        selected = scheduler.compute_schedule_for_date(
            target_date=date(2026, 8, 11),
            rates=[after_midnight_local],
            budget_hours=0.5,
            max_price=30.0,
            use_below_average=True,
            blocked_hours=[],
        )

        self.assertIn(after_midnight_local, selected)


class SmartSchedulerBudgetSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = SmartScheduler(SchedulerConfig)
        # UTC instants corresponding to the scheduler's three fixed London
        # windows on 2026-08-11 (BST = UTC+1).
        self.fixed_window_rates = [
            rate("2026-08-10T23:00:00"),  # 00:00 local
            rate("2026-08-10T23:30:00"),  # 00:30 local
            rate("2026-08-11T00:00:00"),  # 01:00 local
            rate("2026-08-11T00:30:00"),  # 01:30 local
            rate("2026-08-11T13:00:00"),  # 14:00 local
            rate("2026-08-11T13:30:00"),  # 14:30 local
            rate("2026-08-11T18:00:00"),  # 19:00 local
            rate("2026-08-11T18:30:00"),  # 19:30 local
        ]

    def compute_with_half_hour_budget(self):
        return self.scheduler.compute_schedule_for_date(
            target_date=date(2026, 8, 11),
            rates=self.fixed_window_rates,
            budget_hours=0.5,
            max_price=30.0,
            use_below_average=True,
            blocked_hours=[],
        )

    def test_current_fixed_windows_select_four_hours_despite_half_hour_budget(self):
        """Document current behavior until the scheduling policy is redesigned."""
        selected = self.compute_with_half_hour_budget()

        self.assertEqual(selected, self.fixed_window_rates)
        self.assertEqual(len(selected) * 0.5, 4.0)

    @unittest.expectedFailure
    def test_daily_heating_budget_should_cap_total_selected_duration(self):
        """Known defect: fixed windows currently override the configured budget."""
        selected = self.compute_with_half_hour_budget()

        self.assertLessEqual(len(selected) * 0.5, 0.5)


if __name__ == "__main__":
    unittest.main()
