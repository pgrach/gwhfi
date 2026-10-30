import unittest
from datetime import datetime, timedelta, timezone

from services.thermostat_cycle_detector import (
    DetectorConfig,
    ThermostatCycleDetector,
)


class ThermostatCycleDetectorTests(unittest.TestCase):
    BASE_TIME = datetime(2026, 10, 30, 19, 0, tzinfo=timezone.utc)

    def make_detector(self, **overrides):
        values = {
            "on_threshold_w": 2_000,
            "off_threshold_w": 100,
            "min_real_heat_minutes": 10,
            "min_real_heat_wh": 250,
            "low_samples_required": 2,
            "chatter_window_minutes": 12,
            "min_chatter_transitions": 3,
            "max_topup_burst_minutes": 3,
            "min_cooldown_minutes": 120,
            "max_deferral_minutes": 240,
            "probe_success_minutes": 10,
            "probe_short_minutes": 3,
            "max_sample_gap_minutes": 3,
        }
        values.update(overrides)
        return ThermostatCycleDetector(DetectorConfig(**values))

    def observe(
        self,
        detector,
        minute,
        power_w,
        *,
        scheduled_on=True,
        relay_commanded_on=True,
        sample_valid=True,
        energy_total_wh=None,
    ):
        return detector.observe(
            now=self.BASE_TIME + timedelta(minutes=minute),
            scheduled_on=scheduled_on,
            relay_commanded_on=relay_commanded_on,
            power_w=power_w,
            energy_total_wh=energy_total_wh,
            sample_valid=sample_valid,
        )

    def establish_real_heat(self, detector, start_minute=0, sample_count=12):
        decision = None
        for offset in range(sample_count):
            decision = self.observe(detector, start_minute + offset, 3_000)
        return decision

    def enter_hold_after_sustained_heat(self, detector):
        self.establish_real_heat(detector)
        first_low = self.observe(detector, 12, 0)
        self.assertFalse(first_low.suppress)
        decision = self.observe(detector, 13, 0)
        self.assertEqual(decision.state, "HOLD")
        self.assertTrue(decision.suppress)
        return decision

    def test_sustained_heat_then_thermostat_open_enters_hold(self):
        detector = self.make_detector()

        heating = self.establish_real_heat(detector)
        self.assertEqual(heating.state, "HEATING")
        self.assertFalse(heating.suppress)

        decision = self.enter_hold_after_sustained_heat(detector)

        self.assertEqual(decision.event, "tank_satisfied")
        self.assertIn("consecutive", decision.reason)
        self.assertEqual(
            decision.hold_until,
            self.BASE_TIME + timedelta(minutes=13 + 120),
        )

    def test_alternating_short_bursts_trigger_chatter_detection(self):
        detector = self.make_detector(low_samples_required=3)
        self.establish_real_heat(detector)

        decision = None
        for minute, power_w in enumerate(
            [0, 3_000, 0, 3_000, 0, 3_000, 0],
            start=12,
        ):
            decision = self.observe(detector, minute, power_w)
            if decision.state == "HOLD":
                break

        self.assertIsNotNone(decision)
        self.assertEqual(decision.state, "HOLD")
        self.assertTrue(decision.suppress)
        self.assertEqual(decision.event, "tank_satisfied")
        self.assertIn("chatter", decision.reason)

    def test_zero_power_without_prior_real_heat_never_means_tank_satisfied(self):
        detector = self.make_detector()

        decisions = [self.observe(detector, minute, 0) for minute in range(20)]

        self.assertTrue(all(decision.state != "HOLD" for decision in decisions))
        self.assertTrue(all(not decision.suppress for decision in decisions))
        self.assertTrue(all(decision.event != "tank_satisfied" for decision in decisions))

    def test_missing_sample_breaks_consecutive_low_evidence(self):
        detector = self.make_detector()
        self.establish_real_heat(detector)

        first_low = self.observe(detector, 12, 0)
        missing = self.observe(
            detector,
            13,
            None,
            sample_valid=False,
        )
        next_low = self.observe(detector, 14, 0)

        self.assertFalse(first_low.suppress)
        self.assertFalse(missing.suppress)
        self.assertNotEqual(next_low.state, "HOLD")

        decision = self.observe(detector, 15, 0)
        self.assertNotEqual(decision.state, "HOLD")
        self.assertFalse(decision.suppress)
        self.assertFalse(decision.evidence["armed"])

    def test_large_gap_requires_real_heat_to_rearm_detector(self):
        detector = self.make_detector()
        self.establish_real_heat(detector)
        self.observe(detector, 30, 0)
        decision = self.observe(detector, 31, 0)

        self.assertNotEqual(decision.state, "HOLD")
        self.assertFalse(decision.evidence["armed"])

    def test_sparse_on_samples_do_not_arm_sustained_heat(self):
        detector = self.make_detector(min_real_heat_minutes=5)

        for minute in (0, 4, 8, 12, 16, 20):
            self.observe(detector, minute, 3_000)
        self.observe(detector, 21, 0)
        decision = self.observe(detector, 22, 0)

        self.assertNotEqual(decision.state, "HOLD")
        self.assertFalse(decision.evidence["armed"])

    def test_hold_suppresses_until_expiry_then_allows_probe(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)

        still_holding = detector.observe(
            now=hold.hold_until - timedelta(minutes=1),
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=0,
            sample_valid=True,
        )
        probe = detector.observe(
            now=hold.hold_until,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )

        self.assertEqual(still_holding.state, "HOLD")
        self.assertTrue(still_holding.suppress)
        self.assertEqual(probe.state, "PROBE")
        self.assertFalse(probe.suppress)
        self.assertEqual(probe.event, "hold_expired")

    def test_short_probe_reenters_hold(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        detector.observe(
            now=hold.hold_until,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )

        detector.observe(
            now=hold.hold_until + timedelta(minutes=1),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=3_000,
            sample_valid=True,
        )
        detector.observe(
            now=hold.hold_until + timedelta(minutes=2),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=0,
            sample_valid=True,
        )
        decision = detector.observe(
            now=hold.hold_until + timedelta(minutes=3),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=0,
            sample_valid=True,
        )

        self.assertEqual(decision.state, "HOLD")
        self.assertTrue(decision.suppress)
        self.assertEqual(decision.event, "probe_short_cycle")
        self.assertGreater(decision.hold_until, hold.hold_until)

    def test_sustained_probe_clears_satisfied_state(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        detector.observe(
            now=hold.hold_until,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )

        decision = None
        for offset in range(1, 12):
            decision = detector.observe(
                now=hold.hold_until + timedelta(minutes=offset),
                scheduled_on=True,
                relay_commanded_on=True,
                power_w=3_000,
                sample_valid=True,
            )
            if decision.event == "probe_recovered":
                break

        self.assertEqual(decision.state, "HEATING")
        self.assertFalse(decision.suppress)
        self.assertEqual(decision.event, "probe_recovered")
        self.assertIsNone(decision.hold_until)

    def test_exported_hold_state_survives_restart(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        saved = detector.export_state()

        restored = ThermostatCycleDetector(detector.config, initial_state=saved)
        decision = restored.observe(
            now=hold.hold_until - timedelta(minutes=30),
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=0,
            sample_valid=True,
        )

        self.assertEqual(decision.state, "HOLD")
        self.assertTrue(decision.suppress)
        self.assertEqual(decision.hold_until, hold.hold_until)
        self.assertEqual(restored.export_state()["state"], "HOLD")

    def test_monotonic_energy_counter_can_arm_completion_detection(self):
        detector = self.make_detector(
            min_real_heat_minutes=60,
            min_real_heat_wh=200,
        )

        self.observe(detector, 0, 3_000, energy_total_wh=1_000)
        self.observe(detector, 1, 3_000, energy_total_wh=1_100)
        self.observe(detector, 2, 3_000, energy_total_wh=1_200)
        self.observe(detector, 3, 0, energy_total_wh=1_200)
        decision = self.observe(detector, 4, 0, energy_total_wh=1_200)

        self.assertEqual(decision.state, "HOLD")
        self.assertTrue(decision.suppress)
        self.assertGreaterEqual(decision.evidence["session_energy_wh"], 200)

    def test_energy_counter_reset_does_not_arm_detector(self):
        detector = self.make_detector(
            min_real_heat_minutes=60,
            min_real_heat_wh=200,
        )

        self.observe(detector, 0, 3_000, energy_total_wh=1_000)
        self.observe(detector, 1, 3_000, energy_total_wh=900)
        self.observe(detector, 2, 0, energy_total_wh=900)
        decision = self.observe(detector, 3, 0, energy_total_wh=900)

        self.assertNotEqual(decision.state, "HOLD")
        self.assertFalse(decision.suppress)
        self.assertEqual(decision.evidence["session_energy_wh"], 0)

    def test_maximum_deferral_allows_heating_even_if_probe_is_short(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        maximum = datetime.fromisoformat(detector.export_state()["max_hold_until"])

        probe = detector.observe(
            now=maximum,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )
        self.assertEqual(probe.state, "PROBE")
        self.assertFalse(probe.suppress)
        self.assertEqual(probe.event, "max_deferral_reached")

        detector.observe(
            now=maximum + timedelta(minutes=1),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=0,
            sample_valid=True,
        )
        decision = detector.observe(
            now=maximum + timedelta(minutes=2),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=0,
            sample_valid=True,
        )

        self.assertEqual(decision.state, "HEATING")
        self.assertFalse(decision.suppress)
        self.assertEqual(decision.event, "max_deferral_override")
        self.assertTrue(decision.evidence["comfort_override_active"])

    def test_stale_energy_delta_after_restart_cannot_arm_detector(self):
        detector = self.make_detector(
            min_real_heat_minutes=60,
            min_real_heat_wh=200,
        )
        self.observe(detector, 0, 3_000, energy_total_wh=1_000)
        saved = detector.export_state()

        restored = ThermostatCycleDetector(detector.config, initial_state=saved)
        first_low = self.observe(restored, 180, 0, energy_total_wh=1_300)
        second_low = self.observe(restored, 181, 0, energy_total_wh=1_300)

        self.assertFalse(first_low.suppress)
        self.assertFalse(second_low.suppress)
        self.assertNotEqual(second_low.state, "HOLD")
        self.assertEqual(second_low.evidence["session_energy_wh"], 0)

    def test_probe_chatter_reenters_hold_before_maximum_deferral(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        detector.observe(
            now=hold.hold_until,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )

        decision = None
        for offset, power_w in enumerate([3_000, 0, 3_000, 0, 3_000], start=1):
            decision = detector.observe(
                now=hold.hold_until + timedelta(minutes=offset),
                scheduled_on=True,
                relay_commanded_on=True,
                power_w=power_w,
                sample_valid=True,
            )

        self.assertEqual(decision.state, "HOLD")
        self.assertTrue(decision.suppress)
        self.assertEqual(decision.event, "probe_short_cycle")

    def test_probe_on_evidence_does_not_cross_unknown_sample(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        detector.observe(
            now=hold.hold_until,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )
        for offset in range(1, 7):
            detector.observe(
                now=hold.hold_until + timedelta(minutes=offset),
                scheduled_on=True,
                relay_commanded_on=True,
                power_w=3_000,
                sample_valid=True,
            )
        detector.observe(
            now=hold.hold_until + timedelta(minutes=7),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=None,
            sample_valid=False,
        )

        decision = None
        for offset in range(8, 14):
            decision = detector.observe(
                now=hold.hold_until + timedelta(minutes=offset),
                scheduled_on=True,
                relay_commanded_on=True,
                power_w=3_000,
                sample_valid=True,
            )

        self.assertEqual(decision.state, "PROBE")
        self.assertNotEqual(decision.event, "probe_recovered")

    def test_probe_off_evidence_does_not_cross_unknown_sample(self):
        detector = self.make_detector()
        hold = self.enter_hold_after_sustained_heat(detector)
        detector.observe(
            now=hold.hold_until,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )
        detector.observe(
            now=hold.hold_until + timedelta(minutes=1),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=0,
            sample_valid=True,
        )
        detector.observe(
            now=hold.hold_until + timedelta(minutes=2),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=None,
            sample_valid=False,
        )
        decision = detector.observe(
            now=hold.hold_until + timedelta(minutes=3),
            scheduled_on=True,
            relay_commanded_on=True,
            power_w=0,
            sample_valid=True,
        )

        self.assertEqual(decision.state, "PROBE")
        self.assertFalse(decision.suppress)

    def test_maximum_deferral_chatter_latches_comfort_override(self):
        detector = self.make_detector()
        self.enter_hold_after_sustained_heat(detector)
        maximum = datetime.fromisoformat(detector.export_state()["max_hold_until"])
        detector.observe(
            now=maximum,
            scheduled_on=True,
            relay_commanded_on=False,
            power_w=None,
            sample_valid=False,
        )

        decisions = []
        for offset in range(1, 25):
            decisions.append(detector.observe(
                now=maximum + timedelta(minutes=offset),
                scheduled_on=True,
                relay_commanded_on=True,
                power_w=3_000 if offset % 2 else 0,
                sample_valid=True,
            ))

        self.assertTrue(any(d.event == "max_deferral_override" for d in decisions))
        self.assertTrue(all(d.state != "HOLD" for d in decisions))
        self.assertTrue(decisions[-1].evidence["comfort_override_active"])

    def test_rapid_duplicate_samples_do_not_count_as_sustained_minutes(self):
        detector = self.make_detector(min_real_heat_minutes=5)
        for _ in range(20):
            detector.observe(
                now=self.BASE_TIME,
                scheduled_on=True,
                relay_commanded_on=True,
                power_w=3_000,
                sample_valid=True,
            )
        self.observe(detector, 1, 0)
        decision = self.observe(detector, 2, 0)

        self.assertNotEqual(decision.state, "HOLD")
        self.assertFalse(decision.evidence["armed"])


if __name__ == "__main__":
    unittest.main()
