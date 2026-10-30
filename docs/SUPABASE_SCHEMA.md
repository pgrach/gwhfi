# Supabase telemetry schema

The checked-in Supabase project is the source of truth for the Phase 1 raw
telemetry schema. The migration is additive: it preserves all existing
`energy_readings` rows and the legacy dashboard RPC while adding collection
lineage, quality metadata, site/device scoping, indexes, and access policies.

## Apply and verify

Link the local Supabase CLI to the production project, review the target, and
then run:

```sh
supabase db push --dry-run
supabase db push
```

For a disposable local database, `supabase db reset` applies the same migration
from an empty project. Do not use `db reset` against production.

Apply the migration before deploying the versioned Railway collector. The new
collector writes columns and the `telemetry_polls` table that do not exist in
the legacy schema.

## Compatibility and idempotency

- Legacy rows keep their original columns and have `NULL` lineage metadata.
- `power_w`, `voltage`, and `energy_total_wh` are nullable. A missing or invalid
  source measurement is stored as `NULL` with a `quality_flags` explanation; it
  must not be converted to zero.
- Those measurement columns use double precision. The follow-up precision
  migration upgrades legacy `real` columns so normal decimal readings are not
  rounded differently from the atomic idempotency check.
- New versioned rows carry `site_id`, `poll_id`, source/receipt timestamps,
  collector identity, sample reason, quality flags, and schema version.
- The collector calls `ingest_telemetry_poll(p_poll, p_readings)` for both
  successes and failures. PostgreSQL validates the complete payload and commits
  the poll plus all channel rows in one transaction. A rejected child therefore
  cannot leave behind a false-success parent. Deterministic retries preserve an
  already committed success, and a later valid retry can atomically promote an
  earlier source failure.
- The unique constraint on `(poll_id, device_id, channel)` is the collector's
  idempotency key. PostgreSQL permits repeated legacy rows because their
  `poll_id` is `NULL`.
- The legacy three-argument `get_downsampled_readings` RPC remains available.
  The scoped RPC accepts `start_time`, `end_time`, `bucket_seconds`,
  `target_site_id`, and `target_device_id`, and filters before grouping.
- During the legacy transition, the scoped RPC also includes rows whose
  `site_id` is `NULL` only when their `device_id` matches the requested physical
  meter. This retains existing single-household history without treating an
  unknown device as part of the requested site.
- Both RPCs intentionally bucket on legacy `created_at` until all deployed
  readers and collectors have completed the timestamp migration.
- `get_energy_counter_series_for_device` returns the latest real non-NULL
  cumulative counter observation in each site/device/channel time bucket. It
  preserves the observation's actual `created_at`; counters are never averaged.
  Range-boundary bracket observations remain small direct queries in the API.
  The current dashboard uses five-minute buckets for responsive historical
  price statistics; raw one-minute observations remain the authoritative
  source for later episode reconstruction and higher-precision tariff
  attribution.

## Access model and current exception

The dashboard still has no household authentication. To preserve the live
site during Phase 1, `anon` and `authenticated` retain read-only access to
`energy_readings` and the read-only dashboard RPCs. This means raw household power
telemetry remains publicly readable to anyone holding the public anon key.
Site/device filtering prevents accidental mixing in the application; it is
not an authorization boundary.

All direct writes to `energy_readings` and all access to `telemetry_polls`
require Supabase's server-side `service_role` key. Railway's `SUPABASE_KEY`
must therefore be the service-role secret. It must never be exposed through a
`NEXT_PUBLIC_*` variable, committed to the repository, or sent to a browser.
The browser uses only `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

Household-scoped RLS requires authenticated user-to-site membership and is a
separate migration. Do not describe the current anonymous read policy as
household isolation.

## Capacity and retention

At the Phase 1 one-minute cadence with two meter channels, one household adds
approximately 525,600 poll rows plus 1,051,200 reading rows per year: about
1.58 million rows before indexes and raw error payloads. Configure database-size
alerts and review storage, index growth, query latency, and backup size during
rollout.

There is deliberately no destructive retention job in Phase 1. Raw observations
are the evidence needed to reconstruct heater episodes and train or audit later
models. Define an archive format, restore test, and accepted training horizon
before introducing partition expiry or deletion.

## Thermostat-cycle control state

The thermostat-cycle controller persists its latest restart state in
`heater_control_state` and writes append-only decision evidence to
`heater_control_events`. Critical state such as the hold deadline, most recent
confirmed tank-satisfied time, delivered session energy at the last transition,
detector version, and shadow/live mode therefore survive Railway restarts. A
versioned `state_payload` preserves the rolling window and counters captured at
each transition. Evidence accumulated after that transition may be lost on a
restart, which is deliberately conservative: the detector must observe enough
real heat again before it may suppress a scheduled request.

Both tables are service-only: `anon` and `authenticated` have no privileges or
RLS policy. The Railway controller writes them with the same server-side
`service_role` key used for telemetry ingestion. Browser-facing summaries must
be introduced through a separately reviewed read-only view or RPC rather than
granting direct access to raw control evidence.

Each event carries a controller-generated `event_id` idempotency key. A retried
write can safely use an upsert without duplicating training or audit evidence.
There is no automatic retention policy; control events are part of the durable
history needed to tune and validate future demand models.
