"""Durable state and audit events for thermostat-cycle inference."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import uuid

import requests


logger = logging.getLogger(__name__)

MODE_MAP = {
    "IDLE": "idle",
    "HEATING": "heating",
    "HOLD": "holding",
    "PROBE": "probing",
}


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Persisted thermostat timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


class ThermostatStateStorage:
    """Service-role-only REST client for detector transitions."""

    def __init__(self, site_id="home", heater_key="off_peak"):
        self.supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.site_id = (site_id or "home").strip()
        self.heater_key = heater_key
        self.enabled = bool(self.supabase_url and self.supabase_key and self.site_id)
        self.timeout = 5
        self.headers = {
            "apikey": self.supabase_key or "",
            "Authorization": f"Bearer {self.supabase_key or ''}",
            "Content-Type": "application/json",
        }
        if not self.enabled:
            logger.warning("Thermostat state persistence disabled: Supabase configuration missing.")

    def load_state(self, live_only=False):
        if not self.enabled:
            return None
        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/heater_control_state",
                headers=self.headers,
                params={
                    "site_id": f"eq.{self.site_id}",
                    "heater_key": f"eq.{self.heater_key}",
                    "select": "state_payload,shadow_mode",
                    "limit": "1",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            rows = response.json()
            if live_only and isinstance(rows, list) and rows and rows[0].get("shadow_mode") is True:
                logger.info("Ignoring persisted shadow thermostat state during live startup.")
                return None
            if isinstance(rows, list) and rows and isinstance(rows[0].get("state_payload"), dict):
                return rows[0]["state_payload"]
        except (requests.RequestException, TypeError, ValueError) as exc:
            logger.warning("Unable to restore thermostat detector state: %s", exc)
        return None

    def save_transition(
        self,
        *,
        occurred_at,
        state_payload,
        mode_before,
        mode_after,
        event_type,
        shadow_mode,
        relay_commanded_on,
        power_w,
        energy_total_wh,
        evidence,
        policy_version,
        slot=None,
    ):
        if not self.enabled:
            return False

        occurred_iso = _iso(occurred_at)
        mapped_before = MODE_MAP.get(mode_before, str(mode_before).lower() if mode_before else None)
        mapped_after = MODE_MAP.get(mode_after, str(mode_after).lower())
        hold_until = state_payload.get("hold_until")
        state_row = {
            "site_id": self.site_id,
            "heater_key": self.heater_key,
            "mode": mapped_after,
            "policy_version": policy_version,
            "shadow_mode": bool(shadow_mode),
            "hold_until": hold_until,
            "tank_satisfied_at": state_payload.get("tank_satisfied_at"),
            "heat_session_started_at": state_payload.get("heating_started_at"),
            "last_transition_at": occurred_iso,
            "session_energy_wh": max(0.0, float(state_payload.get("session_energy_wh", 0.0))),
            "state_payload": state_payload,
            "evidence": evidence or {},
            "updated_at": occurred_iso,
        }
        # Do not clear the last confirmed sustained-demand timestamp on an
        # unrelated transition. PostgREST merge-upserts only update columns
        # present in the payload, so omission preserves the prior evidence.
        if event_type == "probe_recovered":
            state_row["last_sustained_heat_at"] = occurred_iso

        event_seed = (
            f"{self.site_id}:{self.heater_key}:{occurred_iso}:"
            f"{event_type}:{mapped_before}:{mapped_after}:{policy_version}"
        )
        event_row = {
            "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"gwhfi-control:{event_seed}")),
            "site_id": self.site_id,
            "heater_key": self.heater_key,
            "occurred_at": occurred_iso,
            "event_type": event_type,
            "mode_before": mapped_before,
            "mode_after": mapped_after,
            "policy_version": policy_version,
            "shadow_mode": bool(shadow_mode),
            "relay_commanded_on": bool(relay_commanded_on),
            "observed_power_w": power_w,
            "session_energy_wh": state_payload.get("session_energy_wh"),
            "scheduled_slot_start": _iso(slot.get("valid_from")) if slot else None,
            "scheduled_slot_end": _iso(slot.get("valid_to")) if slot else None,
            "evidence": evidence or {},
        }

        try:
            # Insert immutable evidence first. If the subsequent state upsert
            # fails, a retry reuses the deterministic event id and can safely
            # finish the state write without having exposed an un-audited HOLD
            # as restorable live state.
            event_response = requests.post(
                f"{self.supabase_url}/rest/v1/heater_control_events",
                params={"on_conflict": "event_id"},
                headers={
                    **self.headers,
                    "Prefer": "resolution=ignore-duplicates,return=minimal",
                },
                json=event_row,
                timeout=self.timeout,
            )
            event_response.raise_for_status()

            state_response = requests.post(
                f"{self.supabase_url}/rest/v1/heater_control_state",
                params={"on_conflict": "site_id,heater_key"},
                headers={
                    **self.headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                json=state_row,
                timeout=self.timeout,
            )
            state_response.raise_for_status()
            return True
        except (requests.RequestException, TypeError, ValueError) as exc:
            logger.warning("Unable to persist thermostat transition: %s", exc)
            return False
