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

    def test_daily_heating_budget_caps_fixed_windows(self):
        selected = self.compute_with_half_hour_budget()

        self.assertEqual(selected, [self.fixed_window_rates[3]])
        self.assertEqual(len(selected) * 0.5, 0.5)


class SmartSchedulerHighPriceFallbackTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = SmartScheduler(SchedulerConfig)
        self.target_date = date(2026, 8, 11)

    def compute(self, rates, budget_hours=5.0, blocked_hours=None, not_before=None):
        return self.scheduler.compute_schedule_for_date(
            target_date=self.target_date,
            rates=rates,
            budget_hours=budget_hours,
            max_price=30.0,
            use_below_average=True,
            blocked_hours=blocked_hours or [],
            not_before=not_before,
        )

    def test_all_expensive_rates_still_fill_daily_allowance(self):
        readiness = [
            rate("2026-08-10T23:00:00", 50.0),  # 00:00 local
            rate("2026-08-10T23:30:00", 45.0),  # 00:30 local
            rate("2026-08-11T00:00:00", 43.0),  # 01:00 local
            rate("2026-08-11T00:30:00", 41.0),  # 01:30 local
            rate("2026-08-11T13:00:00", 55.0),  # 14:00 local
            rate("2026-08-11T13:30:00", 52.0),  # 14:30 local
            rate("2026-08-11T18:00:00", 60.0),  # 19:00 local
            rate("2026-08-11T18:30:00", 58.0),  # 19:30 local
        ]
        discretionary = [
            rate("2026-08-11T09:00:00", 34.0),  # 10:00 local
            rate("2026-08-11T09:30:00", 35.0),  # 10:30 local
            rate("2026-08-11T10:00:00", 36.0),  # 11:00 local
            rate("2026-08-11T10:30:00", 37.0),  # 11:30 local
        ]
        blocked_bargain = rate("2026-08-11T15:00:00", 1.0)  # 16:00 local

        selected = self.compute(
            readiness + discretionary + [blocked_bargain],
            blocked_hours=[16],
        )

        self.assertEqual(len(selected), 10)
        self.assertEqual(len({slot["valid_from"] for slot in selected}), 10)
        self.assertTrue(all(slot["value_inc_vat"] > 30.0 for slot in selected))
        self.assertTrue(all(slot in selected for slot in readiness))
        self.assertIn(discretionary[0], selected)
        self.assertIn(discretionary[1], selected)
        self.assertNotIn(discretionary[2], selected)
        self.assertNotIn(discretionary[3], selected)
        self.assertNotIn(blocked_bargain, selected)

    def test_partial_preferred_supply_is_topped_up_above_cap(self):
        rates = [
            rate("2026-08-10T23:00:00", 20.0),
            rate("2026-08-10T23:30:00", 21.0),
            rate("2026-08-11T00:00:00", 40.0),
            rate("2026-08-11T00:30:00", 41.0),
        ]

        selected = self.compute(rates, budget_hours=2.0)

        self.assertEqual(len(selected), 4)
        self.assertEqual(
            {slot["valid_from"] for slot in selected},
            {slot["valid_from"] for slot in rates},
        )

    def test_zero_budget_selects_no_slots(self):
        selected = self.compute([rate("2026-08-10T23:00:00", 40.0)], budget_hours=0)

        self.assertEqual(selected, [])

    def test_insufficient_rates_selects_every_unblocked_slot_without_duplicates(self):
        available = [
            rate("2026-08-10T23:00:00", 40.0),
            rate("2026-08-11T13:00:00", 45.0),
            rate("2026-08-11T18:00:00", 50.0),
        ]

        selected = self.compute(available, budget_hours=5.0)

        self.assertEqual(selected, available)

    def test_same_day_recompute_does_not_spend_budget_on_expired_slots(self):
        expired = [
            rate("2026-08-10T23:00:00", 10.0),
            rate("2026-08-10T23:30:00", 11.0),
            rate("2026-08-11T00:00:00", 12.0),
            rate("2026-08-11T00:30:00", 13.0),
        ]
        future = [
            rate("2026-08-11T13:00:00", 40.0),
            rate("2026-08-11T13:30:00", 41.0),
            rate("2026-08-11T18:00:00", 42.0),
            rate("2026-08-11T18:30:00", 43.0),
        ]
        as_of = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

        selected = self.compute(expired + future, budget_hours=2.0, not_before=as_of)

        self.assertEqual(
            {slot["valid_from"] for slot in selected},
            {slot["valid_from"] for slot in future},
        )


if __name__ == "__main__":
    unittest.main()

