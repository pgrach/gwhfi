# Savings baseline

**Version:** `orbis-2026-06-03_2026-08-10-v1`

**Scope:** storage immersion, meter `48e72969030f`, channel 1

**Local time:** `Europe/London`

## Verified Orbis-only period

The baseline uses the 69 complete days from **2026-06-03 through 2026-08-10**, inclusive. During this period the Orbis timer left the storage immersion available except for its fixed **16:00–19:00** cutoff; the mechanical thermostat cycled the element independently of Agile prices.

Supabase validation for the accepted period:

| Metric | Value |
| --- | ---: |
| Accepted days | 69 |
| Measured energy | 243.005 kWh |
| Mean daily energy | 3.522 kWh |
| Median daily energy | 3.495 kWh |
| Mean starts per day | 28.48 |
| Median starts per day | 30 |
| Mean active hours per day | 15.28 |

Only six active samples fell inside the nominal cutoff. All were at **16:05 or 16:06**, on 2026-06-10, 2026-06-17, 2026-07-02, 2026-07-10, or 2026-07-26. This tightly bounded timer-edge behaviour is retained in the validation record but does not change the baseline boundary.

## Excluded boundaries

- **2026-06-02:** transition day; the heater resumed part-way through the day and does not represent a complete Orbis day.
- **2026-08-11:** transition/installation day; it is not a complete day under one control regime.
- **From 2026-08-12:** the power trace changes to the new smart-control regime and follows selected schedule windows, so these dates are not Orbis baseline observations.

## Counterfactual method

The baseline contains separate normalized profiles for weekdays and weekends, using the 42 allowed half-hours outside the six-half-hour Orbis cutoff. For each evaluated day:

1. Take that day's **measured storage-heater kWh**; do not substitute a fixed baseline energy quantity.
2. Distribute the same kWh across the appropriate weekday or weekend Orbis profile.
3. Price each half-hour allocation using that day's actual Agile tariff.
4. Compare the resulting Orbis counterfactual cost with the measured cost.

This estimates tariff-shifting value only: what the same measured energy would have cost under the observed Orbis timing pattern. It does **not** claim that the controller reduced energy consumption.

## Limitations

- The reference period is a single home's summer sample. Heat loss, inlet-water temperature, occupancy, and hot-water demand may differ in other seasons.
- Tank temperature and water draw were not measured. Element cycling is observable, but its thermal cause cannot be labelled directly.
- Legacy telemetry before the fixed-cadence collector omitted repeated zero-power rows. Energy calculations therefore use cumulative meter counters; row counts are not energy or duration.
- The weekday/weekend split captures only a coarse demand pattern. Any material change to the accepted dates, meter/channel, slot construction, or segmentation requires a new version identifier and revalidation.
