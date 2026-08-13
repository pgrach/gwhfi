-- Preserve Shelly measurements at the same precision used by the atomic
-- ingestion function. Older production installations created these columns as
-- PostgreSQL `real` (float4). Rounding a JSON double to float4 made the
-- function's post-insert idempotency check reject ordinary decimal readings.

begin;

alter table public.energy_readings
    alter column power_w type double precision using power_w::double precision,
    alter column voltage type double precision using voltage::double precision,
    alter column energy_total_wh type double precision using energy_total_wh::double precision;

comment on column public.energy_readings.power_w is
    'Raw Shelly power observation in watts; double precision prevents ingestion-time rounding conflicts.';
comment on column public.energy_readings.voltage is
    'Raw Shelly voltage observation in volts; double precision prevents ingestion-time rounding conflicts.';
comment on column public.energy_readings.energy_total_wh is
    'Raw cumulative Shelly import counter in watt-hours; double precision preserves future observations.';

commit;
