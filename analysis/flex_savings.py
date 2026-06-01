#!/usr/bin/env python3
"""
Estimate value delivered by flexible heater scheduling.

The analysis compares measured heater energy against a counterfactual thermostat
profile learned from a baseline day, e.g. 2026-01-19.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


UK_TZ = ZoneInfo("Europe/London")
POWER_ON_THRESHOLD_W = 100.0
PEAK_WINDOW_START_HOUR = 16
PEAK_WINDOW_END_HOUR = 19
MAX_PLAUSIBLE_CHANNEL_POWER_W = 20000.0


@dataclass
class Reading:
    channel: int
    created_at: datetime
    power_w: float
    energy_total_wh: float


@dataclass
class Rate:
    valid_from: datetime
    valid_to: datetime
    price_ppkwh: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate flexible heater scheduling value.")
    parser.add_argument("--baseline-date", default="2026-01-19", help="UK date to use as thermostat baseline profile.")
    parser.add_argument("--start", default=None, help="UK start date inclusive. Defaults to the day after baseline date.")
    parser.add_argument("--end", default=None, help="UK end date inclusive. Defaults to yesterday.")
    parser.add_argument("--channels", default="0,1", help="Comma-separated Shelly channels to include in actual usage.")
    parser.add_argument("--output-dir", default="analysis/output", help="Directory for CSV/Markdown outputs.")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_environment() -> None:
    root = Path(__file__).resolve().parents[1]
    load_env_file(root / ".env")
    load_env_file(root / "ingestion" / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def uk_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UK_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def daterange(start_day: date, end_day: date):
    current = start_day
    while current <= end_day:
        yield current
        current += timedelta(days=1)


def http_json(url: str, headers: dict[str, str] | None = None) -> object:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def supabase_rows(
    table: str,
    params: list[tuple[str, str]],
    page_size: int = 1000,
) -> list[dict]:
    supabase_url = require_env("SUPABASE_URL").rstrip("/")
    supabase_key = require_env("SUPABASE_KEY")
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }
    rows: list[dict] = []
    offset = 0

    while True:
        query = urllib.parse.urlencode(params, doseq=True, safe=",.:()+")
        url = f"{supabase_url}/rest/v1/{table}?{query}"
        page_headers = dict(headers)
        page_headers["Range"] = f"{offset}-{offset + page_size - 1}"
        page = http_json(url, headers=page_headers)
        if not isinstance(page, list):
            raise RuntimeError(f"Unexpected Supabase response for {table}: {page}")

        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    return rows


def fetch_readings(channel: int, start_utc: datetime, end_utc: datetime) -> list[Reading]:
    previous = supabase_rows(
        "energy_readings",
        [
            ("select", "channel,power_w,energy_total_wh,created_at"),
            ("channel", f"eq.{channel}"),
            ("created_at", f"lt.{utc_iso(start_utc)}"),
            ("order", "created_at.desc"),
            ("limit", "1"),
        ],
    )
    rows = supabase_rows(
        "energy_readings",
        [
            ("select", "channel,power_w,energy_total_wh,created_at"),
            ("channel", f"eq.{channel}"),
            ("created_at", f"gte.{utc_iso(start_utc)}"),
            ("created_at", f"lte.{utc_iso(end_utc)}"),
            ("order", "created_at.asc"),
        ],
    )

    result: list[Reading] = []
    for row in list(reversed(previous)) + rows:
        result.append(
            Reading(
                channel=int(row["channel"]),
                created_at=parse_datetime(row["created_at"]),
                power_w=float(row.get("power_w") or 0),
                energy_total_wh=float(row.get("energy_total_wh") or 0),
            )
        )
    return result


def fetch_rates(start_utc: datetime, end_utc: datetime) -> list[Rate]:
    product = os.getenv("OCTOPUS_PRODUCT_CODE", "AGILE-24-10-01")
    region = os.getenv("OCTOPUS_REGION_CODE", "C")
    tariff = f"E-1R-{product}-{region}"
    base = f"https://api.octopus.energy/v1/products/{product}/electricity-tariffs/{tariff}/standard-unit-rates/"
    query = urllib.parse.urlencode(
        {
            "period_from": utc_iso(start_utc),
            "period_to": utc_iso(end_utc),
            "page_size": "1500",
        }
    )

    rates: list[Rate] = []
    next_url = f"{base}?{query}"
    while next_url:
        data = http_json(next_url)
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected Octopus response: {data}")

        for item in data.get("results", []):
            rates.append(
                Rate(
                    valid_from=parse_datetime(item["valid_from"]),
                    valid_to=parse_datetime(item["valid_to"]),
                    price_ppkwh=float(item["value_inc_vat"]),
                )
            )
        next_url = data.get("next") or ""

    rates.sort(key=lambda rate: rate.valid_from)
    return rates


def overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return 0.0
    return (end - start).total_seconds()


def local_slot_bounds(day: date, slot_index: int) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day, time.min, tzinfo=UK_TZ) + timedelta(minutes=30 * slot_index)
    end_local = start_local + timedelta(minutes=30)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def allocate_segment_to_slots(
    slots_kwh: list[float],
    day: date,
    segment_start: datetime,
    segment_end: datetime,
    segment_kwh: float,
) -> None:
    duration = (segment_end - segment_start).total_seconds()
    if duration <= 0 or segment_kwh <= 0:
        return

    for slot_index in range(48):
        slot_start, slot_end = local_slot_bounds(day, slot_index)
        seconds = overlap_seconds(segment_start, segment_end, slot_start, slot_end)
        if seconds > 0:
            slots_kwh[slot_index] += segment_kwh * (seconds / duration)


def cost_for_energy_window(
    rates: list[Rate],
    segment_start: datetime,
    segment_end: datetime,
    segment_kwh: float,
) -> tuple[float, float]:
    duration = (segment_end - segment_start).total_seconds()
    if duration <= 0 or segment_kwh <= 0:
        return 0.0, 0.0

    priced_kwh = 0.0
    cost_pence = 0.0
    for rate in rates:
        seconds = overlap_seconds(segment_start, segment_end, rate.valid_from, rate.valid_to)
        if seconds <= 0:
            continue

        kwh = segment_kwh * (seconds / duration)
        priced_kwh += kwh
        cost_pence += kwh * rate.price_ppkwh

    return priced_kwh, cost_pence


def clipped_segment_kwh(previous: Reading, current: Reading) -> tuple[float, float]:
    full_duration = (current.created_at - previous.created_at).total_seconds()
    if full_duration <= 0:
        return 0.0, 0.0

    delta_wh = current.energy_total_wh - previous.energy_total_wh
    if delta_wh <= 0:
        return 0.0, full_duration

    implied_power_w = delta_wh / (full_duration / 3600.0)
    if implied_power_w > MAX_PLAUSIBLE_CHANNEL_POWER_W:
        return 0.0, full_duration

    return delta_wh / 1000.0, full_duration


def price_for_slot(rates: list[Rate], slot_start: datetime, slot_end: datetime) -> float | None:
    weighted = 0.0
    seconds_total = 0.0
    for rate in rates:
        seconds = overlap_seconds(slot_start, slot_end, rate.valid_from, rate.valid_to)
        if seconds > 0:
            weighted += rate.price_ppkwh * seconds
            seconds_total += seconds
    if seconds_total <= 0:
        return None
    return weighted / seconds_total


def starts_for_readings(readings: list[Reading], start_utc: datetime, end_utc: datetime) -> int:
    if not readings:
        return 0

    starts = 0
    previous_on = readings[0].power_w > POWER_ON_THRESHOLD_W
    for reading in readings[1:]:
        if not (start_utc <= reading.created_at <= end_utc):
            continue

        current_on = reading.power_w > POWER_ON_THRESHOLD_W
        if current_on and not previous_on:
            starts += 1
        previous_on = current_on

    return starts


def actual_for_day(
    day: date,
    readings_by_channel: dict[int, list[Reading]],
    rates: list[Rate],
) -> dict[str, float]:
    start_utc, end_utc = uk_day_bounds(day)
    peak_start_local = datetime.combine(day, time(PEAK_WINDOW_START_HOUR), tzinfo=UK_TZ)
    peak_end_local = datetime.combine(day, time(PEAK_WINDOW_END_HOUR), tzinfo=UK_TZ)
    peak_start_utc = peak_start_local.astimezone(timezone.utc)
    peak_end_utc = peak_end_local.astimezone(timezone.utc)

    totals = {
        "actual_kwh": 0.0,
        "actual_priced_kwh": 0.0,
        "actual_cost_pence": 0.0,
        "actual_peak_kwh": 0.0,
        "actual_peak_cost_pence": 0.0,
        "actual_starts": 0.0,
    }

    for readings in readings_by_channel.values():
        totals["actual_starts"] += starts_for_readings(readings, start_utc, end_utc)

        for previous, current in zip(readings, readings[1:]):
            if current.created_at <= start_utc or previous.created_at >= end_utc:
                continue

            full_segment_kwh, full_duration = clipped_segment_kwh(previous, current)
            if full_segment_kwh <= 0 or full_duration <= 0:
                continue

            segment_start = max(previous.created_at, start_utc)
            segment_end = min(current.created_at, end_utc)
            clipped_duration = (segment_end - segment_start).total_seconds()
            if clipped_duration <= 0:
                continue

            segment_kwh = full_segment_kwh * (clipped_duration / full_duration)
            priced_kwh, cost_pence = cost_for_energy_window(rates, segment_start, segment_end, segment_kwh)
            totals["actual_kwh"] += segment_kwh
            totals["actual_priced_kwh"] += priced_kwh
            totals["actual_cost_pence"] += cost_pence

            peak_seconds = overlap_seconds(segment_start, segment_end, peak_start_utc, peak_end_utc)
            if peak_seconds > 0:
                peak_kwh = segment_kwh * (peak_seconds / clipped_duration)
                _, peak_cost = cost_for_energy_window(rates, max(segment_start, peak_start_utc), min(segment_end, peak_end_utc), peak_kwh)
                totals["actual_peak_kwh"] += peak_kwh
                totals["actual_peak_cost_pence"] += peak_cost

    return totals


def baseline_profile_for_day(
    day: date,
    readings: list[Reading],
) -> tuple[list[float], float, int]:
    start_utc, end_utc = uk_day_bounds(day)
    slots_kwh = [0.0 for _ in range(48)]

    for previous, current in zip(readings, readings[1:]):
        if current.created_at <= start_utc or previous.created_at >= end_utc:
            continue

        full_segment_kwh, full_duration = clipped_segment_kwh(previous, current)
        if full_segment_kwh <= 0 or full_duration <= 0:
            continue

        segment_start = max(previous.created_at, start_utc)
        segment_end = min(current.created_at, end_utc)
        clipped_duration = (segment_end - segment_start).total_seconds()
        if clipped_duration <= 0:
            continue

        segment_kwh = full_segment_kwh * (clipped_duration / full_duration)
        allocate_segment_to_slots(slots_kwh, day, segment_start, segment_end, segment_kwh)

    total_kwh = sum(slots_kwh)
    starts = starts_for_readings(readings, start_utc, end_utc)
    return slots_kwh, total_kwh, starts


def baseline_cost_for_day(
    day: date,
    rates: list[Rate],
    baseline_weights: list[float],
    target_kwh: float,
) -> dict[str, float]:
    peak_kwh = 0.0
    peak_cost_pence = 0.0
    cost_pence = 0.0
    priced_kwh = 0.0

    for slot_index, weight in enumerate(baseline_weights):
        slot_kwh = target_kwh * weight
        if slot_kwh <= 0:
            continue

        slot_start, slot_end = local_slot_bounds(day, slot_index)
        price = price_for_slot(rates, slot_start, slot_end)
        if price is None:
            continue

        priced_kwh += slot_kwh
        cost_pence += slot_kwh * price

        local_hour = (slot_index * 30) // 60
        if PEAK_WINDOW_START_HOUR <= local_hour < PEAK_WINDOW_END_HOUR:
            peak_kwh += slot_kwh
            peak_cost_pence += slot_kwh * price

    return {
        "baseline_kwh": target_kwh,
        "baseline_priced_kwh": priced_kwh,
        "baseline_cost_pence": cost_pence,
        "baseline_peak_kwh": peak_kwh,
        "baseline_peak_cost_pence": peak_cost_pence,
    }


def money(value_pence: float) -> str:
    return f"GBP {value_pence / 100:.2f}"


def price(value_pence_per_kwh: float | None) -> str:
    if value_pence_per_kwh is None:
        return "n/a"
    return f"{value_pence_per_kwh:.2f}p/kWh"


def main() -> int:
    args = parse_args()
    load_environment()

    baseline_day = date.fromisoformat(args.baseline_date)
    default_start = baseline_day + timedelta(days=1)
    yesterday_uk = datetime.now(UK_TZ).date() - timedelta(days=1)
    start_day = date.fromisoformat(args.start) if args.start else default_start
    end_day = date.fromisoformat(args.end) if args.end else yesterday_uk
    channels = [int(item.strip()) for item in args.channels.split(",") if item.strip()]

    if end_day < start_day:
        raise SystemExit("End date must be on or after start date")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis_start_utc, _ = uk_day_bounds(start_day)
    _, analysis_end_utc = uk_day_bounds(end_day)
    baseline_start_utc, baseline_end_utc = uk_day_bounds(baseline_day)
    fetch_start = min(analysis_start_utc, baseline_start_utc)
    fetch_end = max(analysis_end_utc, baseline_end_utc)

    all_rates = fetch_rates(fetch_start, fetch_end)
    readings_by_channel = {
        channel: fetch_readings(channel, fetch_start, fetch_end)
        for channel in channels
    }

    baseline_channel = 1 if 1 in readings_by_channel else channels[0]
    baseline_slots, baseline_total_kwh, baseline_starts = baseline_profile_for_day(
        baseline_day,
        readings_by_channel[baseline_channel],
    )
    if baseline_total_kwh <= 0:
        raise SystemExit(f"Baseline date {baseline_day} has no measured kWh on channel {baseline_channel}")

    baseline_weights = [slot / baseline_total_kwh for slot in baseline_slots]
    baseline_starts_per_kwh = baseline_starts / baseline_total_kwh if baseline_total_kwh else 0.0

    daily_rows: list[dict[str, float | str]] = []
    totals = {
        "days": 0,
        "actual_kwh": 0.0,
        "actual_cost_pence": 0.0,
        "actual_peak_kwh": 0.0,
        "actual_peak_cost_pence": 0.0,
        "actual_starts": 0.0,
        "same_kwh_cost_pence": 0.0,
        "same_kwh_peak_kwh": 0.0,
        "same_kwh_peak_cost_pence": 0.0,
        "same_kwh_starts": 0.0,
        "uniform_same_kwh_cost_pence": 0.0,
        "uniform_same_kwh_peak_kwh": 0.0,
        "uniform_same_kwh_peak_cost_pence": 0.0,
        "thermostat_kwh": 0.0,
        "thermostat_cost_pence": 0.0,
        "thermostat_peak_kwh": 0.0,
        "thermostat_peak_cost_pence": 0.0,
        "thermostat_starts": 0.0,
        "uniform_thermostat_kwh": 0.0,
        "uniform_thermostat_cost_pence": 0.0,
        "uniform_thermostat_peak_kwh": 0.0,
        "uniform_thermostat_peak_cost_pence": 0.0,
    }
    uniform_weights = [1.0 / 48.0 for _ in range(48)]

    for day in daterange(start_day, end_day):
        day_start_utc, day_end_utc = uk_day_bounds(day)
        day_rates = [
            rate for rate in all_rates
            if overlap_seconds(day_start_utc, day_end_utc, rate.valid_from, rate.valid_to) > 0
        ]
        if not day_rates:
            continue

        actual = actual_for_day(day, readings_by_channel, day_rates)
        same_kwh = baseline_cost_for_day(day, day_rates, baseline_weights, actual["actual_kwh"])
        uniform_same_kwh = baseline_cost_for_day(day, day_rates, uniform_weights, actual["actual_kwh"])
        thermostat = baseline_cost_for_day(day, day_rates, baseline_weights, baseline_total_kwh)
        uniform_thermostat = baseline_cost_for_day(day, day_rates, uniform_weights, baseline_total_kwh)

        same_kwh_starts = actual["actual_kwh"] * baseline_starts_per_kwh

        row = {
            "date": day.isoformat(),
            "actual_kwh": actual["actual_kwh"],
            "actual_cost_gbp": actual["actual_cost_pence"] / 100.0,
            "actual_avg_ppkwh": actual["actual_cost_pence"] / actual["actual_kwh"] if actual["actual_kwh"] else 0.0,
            "actual_peak_kwh": actual["actual_peak_kwh"],
            "actual_starts": actual["actual_starts"],
            "same_kwh_baseline_cost_gbp": same_kwh["baseline_cost_pence"] / 100.0,
            "same_kwh_saving_gbp": (same_kwh["baseline_cost_pence"] - actual["actual_cost_pence"]) / 100.0,
            "same_kwh_peak_kwh": same_kwh["baseline_peak_kwh"],
            "same_kwh_expected_starts": same_kwh_starts,
            "uniform_same_kwh_baseline_cost_gbp": uniform_same_kwh["baseline_cost_pence"] / 100.0,
            "uniform_same_kwh_saving_gbp": (uniform_same_kwh["baseline_cost_pence"] - actual["actual_cost_pence"]) / 100.0,
            "uniform_same_kwh_peak_kwh": uniform_same_kwh["baseline_peak_kwh"],
            "thermostat_baseline_kwh": thermostat["baseline_kwh"],
            "thermostat_baseline_cost_gbp": thermostat["baseline_cost_pence"] / 100.0,
            "thermostat_saving_gbp": (thermostat["baseline_cost_pence"] - actual["actual_cost_pence"]) / 100.0,
            "thermostat_peak_kwh": thermostat["baseline_peak_kwh"],
            "thermostat_expected_starts": baseline_starts,
            "uniform_thermostat_baseline_cost_gbp": uniform_thermostat["baseline_cost_pence"] / 100.0,
            "uniform_thermostat_saving_gbp": (uniform_thermostat["baseline_cost_pence"] - actual["actual_cost_pence"]) / 100.0,
            "uniform_thermostat_peak_kwh": uniform_thermostat["baseline_peak_kwh"],
        }
        daily_rows.append(row)

        totals["days"] += 1
        totals["actual_kwh"] += actual["actual_kwh"]
        totals["actual_cost_pence"] += actual["actual_cost_pence"]
        totals["actual_peak_kwh"] += actual["actual_peak_kwh"]
        totals["actual_peak_cost_pence"] += actual["actual_peak_cost_pence"]
        totals["actual_starts"] += actual["actual_starts"]
        totals["same_kwh_cost_pence"] += same_kwh["baseline_cost_pence"]
        totals["same_kwh_peak_kwh"] += same_kwh["baseline_peak_kwh"]
        totals["same_kwh_peak_cost_pence"] += same_kwh["baseline_peak_cost_pence"]
        totals["same_kwh_starts"] += same_kwh_starts
        totals["uniform_same_kwh_cost_pence"] += uniform_same_kwh["baseline_cost_pence"]
        totals["uniform_same_kwh_peak_kwh"] += uniform_same_kwh["baseline_peak_kwh"]
        totals["uniform_same_kwh_peak_cost_pence"] += uniform_same_kwh["baseline_peak_cost_pence"]
        totals["thermostat_kwh"] += thermostat["baseline_kwh"]
        totals["thermostat_cost_pence"] += thermostat["baseline_cost_pence"]
        totals["thermostat_peak_kwh"] += thermostat["baseline_peak_kwh"]
        totals["thermostat_peak_cost_pence"] += thermostat["baseline_peak_cost_pence"]
        totals["thermostat_starts"] += baseline_starts
        totals["uniform_thermostat_kwh"] += uniform_thermostat["baseline_kwh"]
        totals["uniform_thermostat_cost_pence"] += uniform_thermostat["baseline_cost_pence"]
        totals["uniform_thermostat_peak_kwh"] += uniform_thermostat["baseline_peak_kwh"]
        totals["uniform_thermostat_peak_cost_pence"] += uniform_thermostat["baseline_peak_cost_pence"]

    csv_path = output_dir / "flex_savings_daily.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(daily_rows[0].keys()) if daily_rows else [])
        if daily_rows:
            writer.writeheader()
            writer.writerows(daily_rows)

    actual_avg = totals["actual_cost_pence"] / totals["actual_kwh"] if totals["actual_kwh"] else None
    same_kwh_avg = totals["same_kwh_cost_pence"] / totals["actual_kwh"] if totals["actual_kwh"] else None
    uniform_same_kwh_avg = totals["uniform_same_kwh_cost_pence"] / totals["actual_kwh"] if totals["actual_kwh"] else None
    thermostat_avg = totals["thermostat_cost_pence"] / totals["thermostat_kwh"] if totals["thermostat_kwh"] else None
    uniform_thermostat_avg = totals["uniform_thermostat_cost_pence"] / totals["uniform_thermostat_kwh"] if totals["uniform_thermostat_kwh"] else None
    same_kwh_saving = totals["same_kwh_cost_pence"] - totals["actual_cost_pence"]
    uniform_same_kwh_saving = totals["uniform_same_kwh_cost_pence"] - totals["actual_cost_pence"]
    thermostat_saving = totals["thermostat_cost_pence"] - totals["actual_cost_pence"]
    uniform_thermostat_saving = totals["uniform_thermostat_cost_pence"] - totals["actual_cost_pence"]
    starts_avoided_same_kwh = totals["same_kwh_starts"] - totals["actual_starts"]
    starts_avoided_thermostat = totals["thermostat_starts"] - totals["actual_starts"]

    summary_lines = [
        "# Flex Savings Analysis",
        "",
        f"Period: {start_day.isoformat()} to {end_day.isoformat()} ({int(totals['days'])} complete UK days)",
        f"Baseline thermostat profile date: {baseline_day.isoformat()} (channel {baseline_channel})",
        f"Baseline profile: {baseline_total_kwh:.2f} kWh/day, {baseline_starts:.0f} starts/day, {baseline_starts_per_kwh:.2f} starts/kWh",
        "",
        "## Actual measured operation",
        "",
        f"- Energy: {totals['actual_kwh']:.1f} kWh",
        f"- Cost: {money(totals['actual_cost_pence'])}",
        f"- Average paid unit rate: {price(actual_avg)}",
        f"- 16:00-19:00 energy: {totals['actual_peak_kwh']:.1f} kWh",
        f"- Start events: {totals['actual_starts']:.0f}",
        "",
        "## Conservative counterfactual: same kWh, old thermostat timing",
        "",
        "This isolates tariff shifting value. It assumes the same daily kWh was needed, but spread through the day like the baseline thermostat profile.",
        "",
        f"- Baseline cost: {money(totals['same_kwh_cost_pence'])}",
        f"- Baseline average unit rate: {price(same_kwh_avg)}",
        f"- Estimated tariff-shifting saving: {money(same_kwh_saving)}",
        f"- Baseline 16:00-19:00 energy: {totals['same_kwh_peak_kwh']:.1f} kWh",
        f"- Estimated starts avoided: {starts_avoided_same_kwh:.0f}",
        "",
        "## All-day thermostat counterfactual: same kWh, no tariff awareness",
        "",
        "This also keeps daily kWh equal to actual, but spreads it evenly through the day to represent thermostatic maintenance that would keep cycling through 16:00-19:00.",
        "",
        f"- Baseline cost: {money(totals['uniform_same_kwh_cost_pence'])}",
        f"- Baseline average unit rate: {price(uniform_same_kwh_avg)}",
        f"- Estimated tariff-shifting saving: {money(uniform_same_kwh_saving)}",
        f"- Baseline 16:00-19:00 energy: {totals['uniform_same_kwh_peak_kwh']:.1f} kWh",
        f"- Estimated starts avoided: {starts_avoided_same_kwh:.0f}",
        "",
        "## Wider counterfactual: old thermostat maintained temperature every day",
        "",
        "This estimates what would have happened if the heater kept repeating the measured baseline-day timing every day.",
        "",
        f"- Baseline energy: {totals['thermostat_kwh']:.1f} kWh",
        f"- Baseline cost: {money(totals['thermostat_cost_pence'])}",
        f"- Baseline average unit rate: {price(thermostat_avg)}",
        f"- Estimated total saving versus actual: {money(thermostat_saving)}",
        f"- Baseline 16:00-19:00 energy: {totals['thermostat_peak_kwh']:.1f} kWh",
        f"- Estimated starts avoided: {starts_avoided_thermostat:.0f}",
        "",
        "## Wider all-day thermostat counterfactual",
        "",
        "This uses the baseline day's total kWh and starts, but spreads maintenance evenly through the day, including 16:00-19:00.",
        "",
        f"- Baseline energy: {totals['uniform_thermostat_kwh']:.1f} kWh",
        f"- Baseline cost: {money(totals['uniform_thermostat_cost_pence'])}",
        f"- Baseline average unit rate: {price(uniform_thermostat_avg)}",
        f"- Estimated total saving versus actual: {money(uniform_thermostat_saving)}",
        f"- Baseline 16:00-19:00 energy: {totals['uniform_thermostat_peak_kwh']:.1f} kWh",
        f"- Estimated starts avoided: {starts_avoided_thermostat:.0f}",
        "",
        "## Method notes",
        "",
        "- Actual cost uses measured Shelly cumulative kWh deltas priced against Octopus Agile half-hour intervals.",
        f"- Implausible per-channel counter jumps above {MAX_PLAUSIBLE_CHANNEL_POWER_W:.0f}W average between readings are ignored.",
        "- Baseline timing uses the 30-minute energy distribution from the baseline date.",
        "- The conservative model avoids claiming energy reduction; it only values moving the same kWh away from expensive periods.",
        "- The all-day models are better for the assumption that thermostat maintenance would keep cycling through 16:00-19:00.",
        "- The wider models include avoided kWh and should be read as thermostat-maintenance scenarios, not guaranteed bill counterfactuals.",
        f"- Daily CSV: `{csv_path}`",
        "",
    ]
    summary_path = output_dir / "flex_savings_summary.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
