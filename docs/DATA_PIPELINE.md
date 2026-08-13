# Heater Data Pipeline

This document defines the Phase 1 telemetry contract and the meaning of the
signals retained by the application. The aim is to preserve trustworthy raw
evidence for dashboarding, later analysis, and possible demand forecasting.

## Physical system

The Megaflo DD210 immersion heaters each use a mechanical thermostat and
thermal cut-out. The thermostat opens the element circuit when its local probe
reaches the set point, but it does not expose a readable temperature value.

The following timelines are therefore different and must remain separate:

1. **Schedule intent** -- a tariff interval selected by the controller.
2. **Relay state** -- whether the Shelly relay was commanded and confirmed ON.
3. **Element load** -- power measured by the separate Shelly energy meter.
4. **Thermal state** -- currently unmeasured.
5. **Water draw** -- currently unmeasured.

When a confirmed-ON relay is followed by a fall from normal element power to
zero, the mechanical thermostat opening is a useful inference. It is not a
measured tank temperature and it is not proof that hot water was used.

## Phase 1 principles

- Railway runs the one authoritative telemetry collector.
- Both meter channels are observed on a fixed cadence, including measured 0 W.
- A poll identifier and common timestamps link channel readings from the same
  Shelly response.
- Each poll result and all of its channel rows commit through one transactional
  database function; partial success is never recorded as a successful poll.
- Raw observations are append-only and idempotent.
- Missing or invalid source values remain NULL and carry quality flags; they
  are never converted into synthetic zero readings.
- UTC instants are stored as timezone-aware timestamps. Europe/London is used
  only when deriving household calendar features.
- Every query is scoped to a physical meter (and, as the schema evolves, a
  site) before channels are combined.
- Display interpolation is never written back as training data.

## Raw tables

### `telemetry_polls`

One row records each attempted Shelly collection, including failures. It holds
the poll ID, collector and device identity, request/receipt timestamps, latency,
outcome, error information, and schema version.

### `energy_readings`

Existing measurement columns remain compatible with the dashboard. Phase 1
adds the poll ID, source observation/receipt time, collector ID, sample reason,
quality flags, and schema version. Channel rows from one response share the
same poll ID and observation time.

The cumulative energy counter is the preferred source for delivered energy.
Instantaneous power is used to describe element behaviour, not to calculate
energy by counting rows or averaging an outcome-dependent sample stream.

## Derived data (future migration)

Derived datasets must be reproducible and versioned. A future
`heating_episodes_v1` view or table should include:

- physical device/channel and heater role;
- episode start/end and observation uncertainty;
- cumulative-counter energy delta;
- confirmed relay-enabled duration when available;
- measured element-active duration and telemetry coverage;
- preceding inactive duration;
- schedule and tariff-decision identifiers;
- inference version and quality flags.

Suggested inferred labels include `possible_thermostat_open` and
`possible_draw_recovery`. Do not create labels named `tank_full`,
`temperature_reached`, or `water_draw` until those outcomes are directly
measured or explicitly reported.

## Later sensor upgrades

Tank temperature and water-flow measurements are outside Phase 1. If added,
retain the original sensor observations and calibration metadata. A pair of
temperature probes (upper and lower cylinder regions) would reveal usable heat
and stratification better than a single surface reading; a water-flow sensor
would provide the strongest direct demand label. Any work on an immersion
thermostat pocket or mains-voltage assembly must be designed and installed by
a competent professional for that cylinder and its safety approvals.

## Rollout order

1. Verify Railway has the Supabase `service_role` secret and prepare stable
   site, collector, and physical-meter IDs for Railway and Vercel.
2. Disable the scheduled GitHub one-shot collector so two collectors cannot
   overlap. Keep the following migration/deploy steps close together to limit
   the telemetry gap.
3. Apply the additive Supabase migration and verify its functions, indexes,
   grants, and policies before deploying any new collector or frontend code.
4. Deploy the fixed-cadence Railway collector, then deploy the scoped frontend.
5. Verify atomic poll success/failure, both channel cadences, retry idempotency,
   counter totals, and dashboard output.
6. Retain the legacy columns until all consumers use the scoped contract.

At a one-minute cadence with two channels, budget for roughly 1.58 million raw
rows per household per year before indexes. Phase 1 preserves these rows for
model reconstruction; add storage alerts and an archive review, not an
unverified deletion policy.
