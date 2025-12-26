-- Function to get downsampled energy readings
-- Returns average power per channel per time bucket
-- Useful for 7-day (60 min buckets) or 30-day views

create or replace function get_downsampled_readings(
  start_time timestamp with time zone,
  end_time timestamp with time zone,
  bucket_seconds int
)
returns table (
  bucket_time timestamp with time zone,
  channel int,
  avg_power double precision
)
language plpgsql
as $$
begin
  return query
    select
      to_timestamp(floor(extract(epoch from created_at) / bucket_seconds) * bucket_seconds) as bucket_time,
      energy_readings.channel,
      avg(power_w) as avg_power
    from
      energy_readings
    where
      created_at >= start_time
      and created_at <= end_time
    group by
      1, 2
    order by
      1 asc;
end;
$$;
