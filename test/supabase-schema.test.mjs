import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const migration = readFileSync(
    new URL("../supabase/migrations/20260813101500_phase1_telemetry_lineage.sql", import.meta.url),
    "utf8",
)

test("telemetry ingestion is atomic, validated, and service-only", () => {
    assert.match(
        migration,
        /create function public\.ingest_telemetry_poll\(\s*p_poll jsonb,\s*p_readings jsonb\s*\)/s,
    )
    assert.match(migration, /pg_advisory_xact_lock/)
    assert.match(migration, /insert into public\.telemetry_polls/)
    assert.match(migration, /insert into public\.energy_readings/)
    assert.match(migration, /on conflict \(poll_id, device_id, channel\) do nothing/)
    assert.match(migration, /'preserved_success'/)
    assert.match(migration, /'promoted'/)
    assert.match(
        migration,
        /revoke all on function public\.ingest_telemetry_poll\(jsonb, jsonb\)\s+from public, anon, authenticated;/s,
    )
    assert.match(
        migration,
        /grant execute on function public\.ingest_telemetry_poll\(jsonb, jsonb\)\s+to service_role;/s,
    )
})

test("counter RPC returns a real latest observation rather than an average", () => {
    const counterFunction = migration.match(
        /create function public\.get_energy_counter_series_for_device[\s\S]*?end\s+\$function\$;/,
    )?.[0] ?? ""

    assert.match(counterFunction, /select distinct on \(sample\.sample_bucket, sample\.sample_channel\)/)
    assert.match(counterFunction, /sample\.sample_created_at desc/)
    assert.doesNotMatch(counterFunction, /avg\(/i)
})

test("legacy invalid measurements remain nullable with quality metadata", () => {
    assert.match(migration, /alter column power_w drop not null/)
    assert.match(migration, /alter column voltage drop not null/)
    assert.match(migration, /alter column energy_total_wh drop not null/)
    assert.match(migration, /NULL reading\.power_w requires a matching quality flag/)
})

test("scoped telemetry has an index for bounded time scans across channels", () => {
    assert.match(
        migration,
        /on public\.energy_readings \(site_id, device_id, created_at desc, channel\)/,
    )
})
