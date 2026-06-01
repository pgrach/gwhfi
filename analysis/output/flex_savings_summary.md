# Flex Savings Analysis

Period: 2026-01-20 to 2026-05-31 (132 complete UK days)
Baseline thermostat profile date: 2026-01-19 (channel 1)
Baseline profile: 10.27 kWh/day, 72 starts/day, 7.01 starts/kWh

## Actual measured operation

- Energy: 580.1 kWh
- Cost: GBP 89.61
- Average paid unit rate: 15.45p/kWh
- 16:00-19:00 energy: 1.9 kWh
- Start events: 1206

## Conservative counterfactual: same kWh, old thermostat timing

This isolates tariff shifting value. It assumes the same daily kWh was needed, but spread through the day like the baseline thermostat profile.

- Baseline cost: GBP 105.87
- Baseline average unit rate: 18.25p/kWh
- Estimated tariff-shifting saving: GBP 16.26
- Baseline 16:00-19:00 energy: 0.0 kWh
- Estimated starts avoided: 2862

## All-day thermostat counterfactual: same kWh, no tariff awareness

This also keeps daily kWh equal to actual, but spreads it evenly through the day to represent thermostatic maintenance that would keep cycling through 16:00-19:00.

- Baseline cost: GBP 111.01
- Baseline average unit rate: 19.14p/kWh
- Estimated tariff-shifting saving: GBP 21.41
- Baseline 16:00-19:00 energy: 72.5 kWh
- Estimated starts avoided: 2862

## Wider counterfactual: old thermostat maintained temperature every day

This estimates what would have happened if the heater kept repeating the measured baseline-day timing every day.

- Baseline energy: 1355.3 kWh
- Baseline cost: GBP 245.55
- Baseline average unit rate: 18.12p/kWh
- Estimated total saving versus actual: GBP 155.94
- Baseline 16:00-19:00 energy: 0.0 kWh
- Estimated starts avoided: 8298

## Wider all-day thermostat counterfactual

This uses the baseline day's total kWh and starts, but spreads maintenance evenly through the day, including 16:00-19:00.

- Baseline energy: 1355.3 kWh
- Baseline cost: GBP 257.55
- Baseline average unit rate: 19.00p/kWh
- Estimated total saving versus actual: GBP 167.95
- Baseline 16:00-19:00 energy: 169.4 kWh
- Estimated starts avoided: 8298

## Method notes

- Actual cost uses measured Shelly cumulative kWh deltas priced against Octopus Agile half-hour intervals.
- Implausible per-channel counter jumps above 20000W average between readings are ignored.
- Baseline timing uses the 30-minute energy distribution from the baseline date.
- The conservative model avoids claiming energy reduction; it only values moving the same kWh away from expensive periods.
- The all-day models are better for the assumption that thermostat maintenance would keep cycling through 16:00-19:00.
- The wider models include avoided kWh and should be read as thermostat-maintenance scenarios, not guaranteed bill counterfactuals.
- Daily CSV: `analysis\output\flex_savings_daily.csv`
