"""Conservative thermostat-cycle inference for an immersion heater.

The cylinder has no readable temperature sensor.  This detector therefore
requires evidence of useful heating before it will infer that the mechanical
thermostat has reached its set point.  It never executes a relay command; the
controller may consume its decisions in shadow or live mode.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Optional


STATE_VERSION = 1
VALID_STATES = {"IDLE", "HEATING", "HOLD", "PROBE"}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Thermostat detector timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class DetectorConfig:
    on_threshold_w: float = 2000.0
    off_threshold_w: float = 100.0
    min_real_heat_minutes: int = 10
    min_real_heat_wh: float = 250.0
    low_samples_required: int = 2
    chatter_window_minutes: int = 12
    min_chatter_transitions: int = 3
    max_topup_burst_minutes: int = 3
    min_cooldown_minutes: int = 120
    max_deferral_minutes: int = 240
    probe_success_minutes: int = 10
    probe_short_minutes: int = 3
    max_sample_gap_minutes: int = 3

    def __post_init__(self) -> None:
        if self.off_threshold_w < 0 or self.on_threshold_w <= self.off_threshold_w:
            raise ValueError("Power thresholds must define a non-overlapping hysteresis band")
        positive_fields = (
            "min_real_heat_minutes",
            "low_samples_required",
            "chatter_window_minutes",
            "min_chatter_transitions",
            "max_topup_burst_minutes",
            "min_cooldown_minutes",
            "max_deferral_minutes",
            "probe_success_minutes",
            "probe_short_minutes",
            "max_sample_gap_minutes",
        )
        for field in positive_fields:
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} must be positive")
        if self.max_deferral_minutes < self.min_cooldown_minutes:
            raise ValueError("Maximum deferral cannot be shorter than minimum cooldown")


@dataclass(frozen=True)
class DetectorDecision:
    state: str
    suppress: bool
    reason: str
    event: Optional[str]
    hold_until: Optional[datetime]
    evidence: dict[str, Any]


class ThermostatCycleDetector:
    """Detect tank saturation, hold it off, then probe for renewed demand."""

    def __init__(
        self,
        config: Optional[DetectorConfig] = None,
        initial_state: Optional[dict[str, Any]] = None,
    ) -> None:
        self.config = config or DetectorConfig()
        self._reset_all()
        if initial_state:
            self.restore_state(initial_state)

    @property
    def state(self) -> str:
        return self._state

    @property
    def hold_until(self) -> Optional[datetime]:
        return self._hold_until

    def _reset_all(self) -> None:
        self._state = "IDLE"
        self._hold_until: Optional[datetime] = None
        self._max_hold_until: Optional[datetime] = None
        self._tank_satisfied_at: Optional[datetime] = None
        self._heating_started_at: Optional[datetime] = None
        self._probe_started_at: Optional[datetime] = None
        self._last_sample_at: Optional[datetime] = None
        self._last_energy_total_wh: Optional[float] = None
        self._session_energy_wh = 0.0
        self._on_minutes = 0.0
        self._consecutive_on_minutes = 0.0
        self._armed = False
        self._probe_on_minutes = 0.0
        self._probe_last_on_run_minutes = 0.0
        self._probe_off_minutes = 0.0
        self._comfort_override_active = False
        self._consecutive_off = 0
        self._recent_samples: list[dict[str, str]] = []
        self._last_reason = "idle"

    def _reset_session(self, now: Optional[datetime] = None) -> None:
        self._heating_started_at = now
        self._last_sample_at = None
        self._last_energy_total_wh = None
        self._session_energy_wh = 0.0
        self._on_minutes = 0.0
        self._consecutive_on_minutes = 0.0
        self._armed = False
        self._consecutive_off = 0
        self._recent_samples = []

    def export_state(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "state": self._state,
            "hold_until": _iso(self._hold_until),
            "max_hold_until": _iso(self._max_hold_until),
            "tank_satisfied_at": _iso(self._tank_satisfied_at),
            "heating_started_at": _iso(self._heating_started_at),
            "probe_started_at": _iso(self._probe_started_at),
            "last_sample_at": _iso(self._last_sample_at),
            "last_energy_total_wh": self._last_energy_total_wh,
            "session_energy_wh": self._session_energy_wh,
            "on_minutes": self._on_minutes,
            "consecutive_on_minutes": self._consecutive_on_minutes,
            "armed": self._armed,
            "probe_on_minutes": self._probe_on_minutes,
            "probe_last_on_run_minutes": self._probe_last_on_run_minutes,
            "probe_off_minutes": self._probe_off_minutes,
            "comfort_override_active": self._comfort_override_active,
            "consecutive_off": self._consecutive_off,
            "recent_samples": list(self._recent_samples),
            "last_reason": self._last_reason,
            "config": asdict(self.config),
        }

    def restore_state(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or payload.get("version") != STATE_VERSION:
            return
        state = str(payload.get("state", "")).upper()
        if state not in VALID_STATES:
            return

        self._state = state
        self._hold_until = _parse_datetime(payload.get("hold_until"))
        self._max_hold_until = _parse_datetime(payload.get("max_hold_until"))
        self._tank_satisfied_at = _parse_datetime(payload.get("tank_satisfied_at"))
        self._heating_started_at = _parse_datetime(payload.get("heating_started_at"))
        self._probe_started_at = _parse_datetime(payload.get("probe_started_at"))
        self._last_sample_at = _parse_datetime(payload.get("last_sample_at"))

        for attr, key in (
            ("_session_energy_wh", "session_energy_wh"),
            ("_on_minutes", "on_minutes"),
            ("_consecutive_on_minutes", "consecutive_on_minutes"),
            ("_probe_on_minutes", "probe_on_minutes"),
            ("_probe_last_on_run_minutes", "probe_last_on_run_minutes"),
            ("_probe_off_minutes", "probe_off_minutes"),
        ):
            try:
                value = float(payload.get(key, 0.0))
            except (TypeError, ValueError):
                value = 0.0
            setattr(self, attr, max(0.0, value) if math.isfinite(value) else 0.0)

        try:
            energy_total = float(payload.get("last_energy_total_wh"))
            self._last_energy_total_wh = energy_total if math.isfinite(energy_total) else None
        except (TypeError, ValueError):
            self._last_energy_total_wh = None
        try:
            self._consecutive_off = max(0, int(payload.get("consecutive_off", 0)))
        except (TypeError, ValueError):
            self._consecutive_off = 0
        self._armed = payload.get("armed") is True
        self._comfort_override_active = payload.get("comfort_override_active") is True

        self._recent_samples = []
        recent = payload.get("recent_samples", [])
        if isinstance(recent, list):
            for sample in recent:
                if not isinstance(sample, dict) or sample.get("class") not in {"on", "off"}:
                    continue
                at = _parse_datetime(sample.get("at"))
                if at:
                    self._recent_samples.append({"at": _iso(at), "class": sample["class"]})
        self._last_reason = str(payload.get("last_reason") or state.lower())

    def _classify(self, power_w: Optional[float], sample_valid: bool) -> str:
        if not sample_valid or power_w is None:
            return "unknown"
        try:
            power = float(power_w)
        except (TypeError, ValueError):
            return "unknown"
        if not math.isfinite(power) or power < 0:
            return "unknown"
        if power >= self.config.on_threshold_w:
            return "on"
        if power <= self.config.off_threshold_w:
            return "off"
        return "unknown"

    def _record_energy(self, energy_total_wh: Optional[float]) -> None:
        if energy_total_wh is None:
            return
        try:
            current = float(energy_total_wh)
        except (TypeError, ValueError):
            return
        if not math.isfinite(current) or current < 0:
            return
        if self._last_energy_total_wh is not None and current >= self._last_energy_total_wh:
            self._session_energy_wh += current - self._last_energy_total_wh
        self._last_energy_total_wh = current

    def _record_sample(self, now: datetime, classification: str) -> float:
        elapsed_minutes = 0.0
        if self._last_sample_at:
            gap = (now - self._last_sample_at).total_seconds() / 60.0
            if gap < 0 or gap > self.config.max_sample_gap_minutes:
                self._consecutive_off = 0
                self._consecutive_on_minutes = 0.0
                self._on_minutes = 0.0
                self._session_energy_wh = 0.0
                self._armed = False
                self._recent_samples = []
                # A cumulative meter delta across a restart or telemetry gap
                # is not evidence from this heating session. Rebaseline it.
                self._last_energy_total_wh = None
                self._probe_on_minutes = 0.0
                self._probe_last_on_run_minutes = 0.0
                self._probe_off_minutes = 0.0
            else:
                # Count elapsed time, not loop invocations. Duplicate/rapid
                # calls cannot manufacture sustained heating evidence.
                elapsed_minutes = max(0.0, gap)
        self._last_sample_at = now

        if classification == "on":
            self._on_minutes += elapsed_minutes
            self._consecutive_on_minutes += elapsed_minutes
            if self._consecutive_on_minutes >= self.config.min_real_heat_minutes:
                self._armed = True
            self._consecutive_off = 0
        elif classification == "off":
            self._consecutive_on_minutes = 0.0
            self._consecutive_off += 1

        self._recent_samples.append({"at": _iso(now), "class": classification})
        cutoff = now - timedelta(minutes=self.config.chatter_window_minutes)
        self._recent_samples = [
            sample
            for sample in self._recent_samples
            if (_parse_datetime(sample.get("at")) or now) >= cutoff
        ]
        return elapsed_minutes

    def _record_unknown(self, now: datetime) -> None:
        self._last_sample_at = now
        self._last_energy_total_wh = None
        self._consecutive_off = 0
        self._consecutive_on_minutes = 0.0
        self._on_minutes = 0.0
        self._session_energy_wh = 0.0
        self._armed = False
        self._recent_samples = []
        self._probe_on_minutes = 0.0
        self._probe_last_on_run_minutes = 0.0
        self._probe_off_minutes = 0.0

    def _is_armed(self) -> bool:
        if self._session_energy_wh >= self.config.min_real_heat_wh:
            self._armed = True
        return self._armed

    def _is_chattering(self) -> bool:
        classes = [sample["class"] for sample in self._recent_samples]
        if len(classes) < self.config.min_chatter_transitions + 1 or "off" not in classes:
            return False
        first_off = classes.index("off")
        tail = classes[first_off:]
        transitions = sum(left != right for left, right in zip(tail, tail[1:]))
        if transitions < self.config.min_chatter_transitions:
            return False

        runs: list[tuple[str, int]] = []
        for classification in tail:
            if runs and runs[-1][0] == classification:
                runs[-1] = (classification, runs[-1][1] + 1)
            else:
                runs.append((classification, 1))
        topups = [length for classification, length in runs[1:] if classification == "on"]
        return bool(topups) and max(topups) <= self.config.max_topup_burst_minutes

    def _evidence(self, classification: str) -> dict[str, Any]:
        classes = [sample["class"] for sample in self._recent_samples]
        return {
            "classification": classification,
            "on_minutes": round(self._on_minutes, 2),
            "consecutive_on_minutes": round(self._consecutive_on_minutes, 2),
            "armed": self._armed,
            "session_energy_wh": round(self._session_energy_wh, 3),
            "consecutive_off": self._consecutive_off,
            "recent_samples": len(classes),
            "recent_transitions": sum(a != b for a, b in zip(classes, classes[1:])),
            "comfort_override_active": self._comfort_override_active,
        }

    def _decision(
        self,
        *,
        suppress: bool,
        reason: str,
        event: Optional[str] = None,
        classification: str = "unknown",
    ) -> DetectorDecision:
        self._last_reason = reason
        return DetectorDecision(
            state=self._state,
            suppress=suppress,
            reason=reason,
            event=event,
            hold_until=self._hold_until,
            evidence=self._evidence(classification),
        )

    def _enter_hold(self, now: datetime, reason: str, *, preserve_max: bool = False) -> None:
        self._state = "HOLD"
        self._tank_satisfied_at = now
        if not preserve_max or self._max_hold_until is None:
            self._max_hold_until = now + timedelta(minutes=self.config.max_deferral_minutes)
        proposed = now + timedelta(minutes=self.config.min_cooldown_minutes)
        self._hold_until = min(proposed, self._max_hold_until)
        self._probe_started_at = None
        self._probe_on_minutes = 0.0
        self._probe_last_on_run_minutes = 0.0
        self._probe_off_minutes = 0.0
        self._last_reason = reason

    def _enter_comfort_override(self, now: datetime, reason: str) -> None:
        """Keep the relay available after the maximum deferral is exhausted."""
        self._state = "HEATING"
        self._hold_until = None
        self._max_hold_until = None
        self._probe_started_at = None
        self._probe_on_minutes = 0.0
        self._probe_last_on_run_minutes = 0.0
        self._probe_off_minutes = 0.0
        self._reset_session(now)
        self._comfort_override_active = True
        self._last_reason = reason

    def observe(
        self,
        now: datetime,
        scheduled_on: bool,
        relay_commanded_on: bool,
        power_w: Optional[float],
        energy_total_wh: Optional[float] = None,
        sample_valid: bool = True,
    ) -> DetectorDecision:
        now = _aware_utc(now)

        if not scheduled_on:
            if self._state == "HEATING":
                self._state = "IDLE"
                self._reset_session()
                self._comfort_override_active = False
                self._hold_until = None
                self._max_hold_until = None
            elif self._state == "PROBE":
                self._state = "HOLD"
                self._hold_until = now
            return self._decision(suppress=False, reason="no_active_heating_request")

        probe_event = None
        if self._state == "HOLD":
            maximum_reached = self._max_hold_until is not None and now >= self._max_hold_until
            if not maximum_reached and self._hold_until and now < self._hold_until:
                return self._decision(suppress=True, reason="minimum_cooldown_active")
            self._state = "PROBE"
            self._probe_started_at = now
            self._probe_on_minutes = 0.0
            self._probe_last_on_run_minutes = 0.0
            self._probe_off_minutes = 0.0
            self._consecutive_off = 0
            self._recent_samples = []
            self._last_sample_at = None
            probe_event = "max_deferral_reached" if maximum_reached else "hold_expired"

        if self._state == "IDLE":
            self._state = "HEATING"
            self._reset_session(now)

        if not relay_commanded_on:
            return self._decision(
                suppress=False,
                reason="relay_not_commanded_on",
                event=probe_event,
            )

        classification = self._classify(power_w, sample_valid)
        if classification == "unknown":
            self._record_unknown(now)
            return self._decision(
                suppress=False,
                reason="telemetry_unknown",
                event=probe_event,
                classification=classification,
            )

        elapsed_minutes = self._record_sample(now, classification)
        self._record_energy(energy_total_wh)

        if self._state == "PROBE":
            short_cycle = False
            if classification == "on":
                self._probe_on_minutes += elapsed_minutes
                self._probe_off_minutes = 0.0
                if self._probe_on_minutes >= self.config.probe_success_minutes:
                    self._state = "HEATING"
                    self._armed = True
                    self._max_hold_until = None
                    self._hold_until = None
                    return self._decision(
                        suppress=False,
                        reason="sustained_demand_returned",
                        event="probe_recovered",
                        classification=classification,
                    )
            else:
                if self._probe_on_minutes > 0:
                    self._probe_last_on_run_minutes = self._probe_on_minutes
                self._probe_on_minutes = 0.0
                self._probe_off_minutes += 1.0
                short_cycle = (
                    self._probe_off_minutes >= self.config.low_samples_required
                    and self._probe_last_on_run_minutes <= self.config.probe_short_minutes
                )
            if short_cycle or self._is_chattering():
                if self._max_hold_until and now >= self._max_hold_until:
                    self._enter_comfort_override(now, "comfort_override_after_max_deferral")
                    return self._decision(
                        suppress=False,
                        reason="comfort_override_after_max_deferral",
                        event="max_deferral_override",
                        classification=classification,
                    )
                self._enter_hold(now, "probe_short_cycle", preserve_max=True)
                return self._decision(
                    suppress=True,
                    reason="probe_short_cycle",
                    event="probe_short_cycle",
                    classification=classification,
                )
            return self._decision(
                suppress=False,
                reason="probing_for_demand",
                event=probe_event,
                classification=classification,
            )

        if self._state == "HEATING" and self._comfort_override_active:
            recovery_minutes = max(
                self.config.min_real_heat_minutes,
                self.config.probe_success_minutes,
            )
            if (
                classification == "on"
                and self._consecutive_on_minutes >= recovery_minutes
            ):
                self._comfort_override_active = False
                self._armed = True
                return self._decision(
                    suppress=False,
                    reason="sustained_demand_after_comfort_override",
                    event="comfort_demand_recovered",
                    classification=classification,
                )
            return self._decision(
                suppress=False,
                reason="comfort_override_active",
                classification=classification,
            )

        if self._state == "HEATING" and self._is_armed():
            reason = None
            if self._consecutive_off >= self.config.low_samples_required:
                reason = "consecutive_low_power"
            elif self._is_chattering():
                reason = "thermostat_chatter"
            if reason:
                self._enter_hold(now, reason)
                return self._decision(
                    suppress=True,
                    reason=reason,
                    event="tank_satisfied",
                    classification=classification,
                )

        return self._decision(
            suppress=False,
            reason="heating_or_not_yet_armed",
            event=probe_event,
            classification=classification,
        )
