"""Fixed-cadence Shelly Cloud telemetry collector.

Every successful poll stores one observation per returned meter channel.  The
poll UUID and timestamps are shared by all channel rows, making retries
idempotent and preserving zero-power observations for later analysis.
"""

import logging
import math
import os
import time
import uuid
import hashlib
import json
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

try:
    from .services.shelly_rate_gate import SharedShellyRequestGate
except ImportError:  # Direct execution: python ingestion/cloud_worker.py
    from services.shelly_rate_gate import SharedShellyRequestGate


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("cloud_worker.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SHELLY_AUTH_KEY = os.getenv("SHELLY_CLOUD_AUTH_KEY")
SHELLY_SERVER = os.getenv("SHELLY_CLOUD_SERVER")
SHELLY_DEVICE_ID = os.getenv("SHELLY_METER_DEVICE_ID") or os.getenv("SHELLY_DEVICE_ID")
COLLECTOR_ID = os.getenv("TELEMETRY_COLLECTOR_ID", "railway-cloud-worker")
SITE_ID = os.getenv("TELEMETRY_SITE_ID", "home")

POLL_INTERVAL_SECONDS = 60.0
SHELLY_TIMEOUT_SECONDS = 10
SUPABASE_TIMEOUT_SECONDS = 15
MAX_WRITE_ATTEMPTS = 3
SCHEMA_VERSION = 1
EXPECTED_CHANNELS = {0, 1}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_KEY or ''}",
    "Content-Type": "application/json",
}
RPC_HEADERS = {
    **SUPABASE_HEADERS,
    "Prefer": "return=minimal",
}

# This state is informational only and is committed after a successful write.
last_readings = {}
SHELLY_REQUEST_GATE = SharedShellyRequestGate()


def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(value):
    if value.tzinfo is None:
        raise ValueError("Telemetry timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def scheduled_minute(value):
    if value.tzinfo is None:
        raise ValueError("Scheduled telemetry timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def poll_id_for_schedule(value):
    """Return a restart-safe identity for this collector's scheduled minute."""
    identity = "|".join(
        [COLLECTOR_ID, SITE_ID, SHELLY_DEVICE_ID or "", utc_iso(scheduled_minute(value))]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"gwhfi-telemetry:{identity}"))


def hash_payload(payload):
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def configuration_valid():
    required_values = [
        SUPABASE_URL,
        SUPABASE_KEY,
        SHELLY_AUTH_KEY,
        SHELLY_SERVER,
        SHELLY_DEVICE_ID,
        COLLECTOR_ID,
        SITE_ID,
    ]
    return all(isinstance(value, str) and value.strip() for value in required_values)


def _number_or_none(raw_value, field, flags, *, minimum=None, maximum=None):
    if raw_value is None:
        flags.append(f"{field}_missing")
        return None
    if isinstance(raw_value, bool):
        flags.append(f"{field}_invalid")
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        flags.append(f"{field}_invalid")
        return None
    if not math.isfinite(value):
        flags.append(f"{field}_non_finite")
        return None
    if minimum is not None and value < minimum:
        flags.append(f"{field}_out_of_range")
        return None
    if maximum is not None and value > maximum:
        flags.append(f"{field}_out_of_range")
        return None
    return value


def validate_emeter(emeter):
    """Return nullable measurements and explicit quality flags."""
    flags = []
    if not isinstance(emeter, dict):
        return {
            "power_w": None,
            "voltage": None,
            "energy_total_wh": None,
            "quality_flags": ["channel_payload_invalid"],
        }

    return {
        "power_w": _number_or_none(emeter.get("power"), "power", flags, minimum=0, maximum=100_000),
        "voltage": _number_or_none(emeter.get("voltage"), "voltage", flags, minimum=0, maximum=500),
        "energy_total_wh": _number_or_none(
            emeter.get("total"), "energy_total", flags, minimum=0
        ),
        "quality_flags": flags,
    }


def get_shelly_status(device_id):
    """Return ``(status, metadata)`` without manufacturing measurements."""
    url = f"{SHELLY_SERVER}/device/status"
    payload = {"id": device_id, "auth_key": SHELLY_AUTH_KEY}
    request_started = None
    monotonic_started = None
    received_at = None
    response = None
    try:
        # Reserve the shared account-level request slot before recording the
        # actual outbound start. scheduled_at -> request_started_at therefore
        # exposes any queueing delay instead of folding it into HTTP latency.
        SHELLY_REQUEST_GATE.wait_for_turn()
        request_started = utc_now()
        monotonic_started = time.monotonic()
        response = requests.post(url, data=payload, timeout=SHELLY_TIMEOUT_SECONDS)
        received_at = utc_now()
        latency_ms = round((time.monotonic() - monotonic_started) * 1000)
        response.raise_for_status()
        data = response.json()
        if not data.get("isok"):
            logger.error("Shelly API rejected the status request: %s", data)
            return None, {
                "request_started_at": request_started,
                "received_at": received_at,
                "latency_ms": latency_ms,
                "http_status": response.status_code,
                "error_code": "shelly_api_rejected",
                "error_message": "Shelly Cloud returned isok=false",
                "raw_payload": data,
            }
        status = data.get("data", {}).get("device_status")
        if not isinstance(status, dict):
            return None, {
                "request_started_at": request_started,
                "received_at": received_at,
                "latency_ms": latency_ms,
                "http_status": response.status_code,
                "error_code": "invalid_status_payload",
                "error_message": "Shelly Cloud did not return a device_status object",
                "raw_payload": data,
            }
        return status, {
            "request_started_at": request_started,
            "received_at": received_at,
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "error_code": None,
            "error_message": None,
            "raw_payload": None,
        }
    except Exception as exc:
        logger.error("Failed to fetch Shelly status: %s", exc)
        http_status = getattr(getattr(exc, "response", None), "status_code", None)
        if http_status is None and response is not None:
            http_status = getattr(response, "status_code", None)
        raw_payload = None
        if response is not None:
            try:
                raw_payload = response.json()
            except (TypeError, ValueError):
                pass
        return None, {
            "request_started_at": request_started or utc_now(),
            # A transport failure is not a received response. If parsing or
            # HTTP validation failed after receipt, retain the actual instant.
            "received_at": received_at,
            "latency_ms": (
                round((time.monotonic() - monotonic_started) * 1000)
                if monotonic_started is not None
                else None
            ),
            "http_status": http_status,
            "error_code": (
                "shelly_rate_limited" if http_status == 429 else type(exc).__name__
            ),
            "error_message": str(exc),
            "raw_payload": raw_payload,
        }


def returned_emeter_channels(status):
    emeters = status.get("emeters")
    return set(range(len(emeters))) if isinstance(emeters, list) else set()


def build_rows(status, poll_id, observed_at, received_at):
    emeters = status.get("emeters")
    if not isinstance(emeters, list) or not emeters:
        logger.error("Shelly status returned no emeter channels")
        return []

    timestamp = utc_iso(observed_at)
    received_timestamp = utc_iso(received_at)
    rows = []
    for channel, emeter in enumerate(emeters):
        measurement = validate_emeter(emeter)
        rows.append(
            {
                # Legacy dashboard columns remain populated with the same names.
                "device_id": SHELLY_DEVICE_ID,
                "site_id": SITE_ID,
                "channel": channel,
                "power_w": measurement["power_w"],
                "voltage": measurement["voltage"],
                "energy_total_wh": measurement["energy_total_wh"],
                "created_at": timestamp,
                # Phase-1 provenance columns.
                "poll_id": poll_id,
                "observed_at": timestamp,
                "received_at": received_timestamp,
                "collector_id": COLLECTOR_ID,
                "sample_reason": "periodic",
                "quality_flags": measurement["quality_flags"],
                "schema_version": SCHEMA_VERSION,
            }
        )
    returned_channels = {row["channel"] for row in rows}
    if not EXPECTED_CHANNELS.issubset(returned_channels):
        logger.error(
            "Shelly status omitted required meter channels: expected=%s returned=%s",
            sorted(EXPECTED_CHANNELS),
            sorted(returned_channels),
        )
        return []
    return rows


def _post_with_retries(url, payload, *, attempts=MAX_WRITE_ATTEMPTS, headers=None):
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers or SUPABASE_HEADERS,
                timeout=SUPABASE_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Supabase write attempt %s/%s failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    return False


def build_poll_row(
    poll_id,
    scheduled_at,
    metadata,
    outcome,
    *,
    raw_payload=None,
    hashed_payload=None,
    error_code=None,
    error_message=None,
):
    completed_at = utc_now()
    return {
        "poll_id": poll_id,
        "site_id": SITE_ID,
        "device_id": SHELLY_DEVICE_ID,
        "collector_id": COLLECTOR_ID,
        "source": "shelly_cloud",
        "sampling_policy_version": SCHEMA_VERSION,
        "scheduled_at": utc_iso(scheduled_at),
        "request_started_at": utc_iso(metadata["request_started_at"]),
        "received_at": utc_iso(metadata["received_at"]) if metadata.get("received_at") else None,
        "completed_at": utc_iso(completed_at),
        "outcome": outcome,
        "error_code": error_code,
        "error_message": error_message,
        "latency_ms": metadata.get("latency_ms"),
        "http_status": metadata.get("http_status"),
        "payload_hash": hash_payload(
            hashed_payload if hashed_payload is not None else raw_payload
        ),
        "raw_payload": raw_payload,
    }


def persist_poll_result(poll_row, rows):
    """Persist one poll outcome and its channel observations atomically.

    The database RPC owns the transaction and the idempotent conflict handling.
    This prevents a process crash between parent and child writes from leaving a
    poll outcome inconsistent with its readings. Failed source polls pass an
    empty reading list through the same conflict-safe path.
    """
    if poll_row.get("outcome") == "success" and not rows:
        return False
    url = f"{SUPABASE_URL}/rest/v1/rpc/ingest_telemetry_poll"
    payload = {"p_poll": poll_row, "p_readings": rows}
    return _post_with_retries(url, payload, headers=RPC_HEADERS)


def process_reading(*, poll_id=None, scheduled_at=None):
    """Collect and persist one poll; return success for process supervision."""
    if not configuration_valid():
        logger.error("Missing telemetry collector configuration")
        return False

    scheduled_at = scheduled_minute(scheduled_at or utc_now())
    poll_id = poll_id or poll_id_for_schedule(scheduled_at)
    logger.info("Fetching Shelly Cloud status (poll_id=%s)", poll_id)
    status, metadata = get_shelly_status(SHELLY_DEVICE_ID)
    if status is None:
        persist_poll_result(build_poll_row(
            poll_id,
            scheduled_at,
            metadata,
            "source_error",
            raw_payload=metadata.get("raw_payload"),
            hashed_payload=metadata.get("raw_payload"),
            error_code=metadata.get("error_code"),
            error_message=metadata.get("error_message"),
        ), [])
        return False

    # Shelly Gen-1 status has no reliable source observation timestamp. Use one
    # shared receipt instant for every channel and retain request timing metadata
    # for the poll table introduced alongside these additive row columns.
    observed_at = metadata["received_at"]
    rows = build_rows(status, poll_id, observed_at, metadata["received_at"])
    if not rows:
        returned_channels = returned_emeter_channels(status)
        missing_channels = sorted(EXPECTED_CHANNELS - returned_channels)
        error_code = "no_emeter_channels" if not returned_channels else "missing_required_channels"
        error_message = (
            "Shelly status returned no emeter channels"
            if not returned_channels
            else (
                "Shelly status omitted required channels "
                f"{missing_channels}; returned {sorted(returned_channels)}"
            )
        )
        persist_poll_result(build_poll_row(
            poll_id,
            scheduled_at,
            metadata,
            "source_error",
            raw_payload=status,
            hashed_payload=status,
            error_code=error_code,
            error_message=error_message,
        ), [])
        return False

    has_quality_issue = any(row["quality_flags"] for row in rows)
    poll_row = build_poll_row(
        poll_id,
        scheduled_at,
        metadata,
        "success",
        raw_payload=status if has_quality_issue else None,
        hashed_payload=status,
    )
    if not persist_poll_result(poll_row, rows):
        return False

    for row in rows:
        last_readings[(row["device_id"], row["channel"])] = row
    logger.info("Logged %s channel rows (poll_id=%s)", len(rows), poll_id)
    return True


def run_forever(interval_seconds=POLL_INTERVAL_SECONDS):
    """Run on monotonic deadlines so request latency does not accumulate."""
    next_deadline = time.monotonic()
    while True:
        scheduled_at = utc_now()
        try:
            process_reading(scheduled_at=scheduled_at)
        except KeyboardInterrupt:
            logger.info("Worker stopped")
            break
        except Exception:
            logger.exception("Unexpected error in telemetry loop")

        next_deadline += interval_seconds
        now = time.monotonic()
        if next_deadline <= now:
            skipped_intervals = math.floor((now - next_deadline) / interval_seconds) + 1
            next_deadline += skipped_intervals * interval_seconds
        try:
            time.sleep(max(0.0, next_deadline - time.monotonic()))
        except KeyboardInterrupt:
            logger.info("Worker stopped")
            break


def main():
    if not configuration_valid():
        logger.critical(
            "Telemetry collector cannot start: required Supabase or Shelly configuration is missing"
        )
        return 1

    logger.info("Starting authoritative fixed-cadence Shelly telemetry collector")
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
