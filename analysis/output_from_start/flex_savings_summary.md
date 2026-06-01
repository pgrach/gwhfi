# Flex Savings Analysis

Period: 2025-12-18 to 2026-05-31 (165 complete UK days)
Baseline thermostat profile date: 2026-01-19 (channel 1)
Baseline profile: 10.27 kWh/day, 73 starts/day, 7.11 starts/kWh

## Actual measured operation

- Energy: 747.3 kWh
- Cost: GBP 118.01
- Average paid unit rate: 15.79p/kWh
- 16:00-19:00 energy: 2.2 kWh
- Start events: 1740

## Conservative counterfactual: same kWh, old thermostat timing

This isolates tariff shifting value. It assumes the same daily kWh was needed, but spread through the day like the baseline thermostat profile.

- Baseline cost: GBP 136.51
- Baseline average unit rate: 18.27p/kWh
- Estimated tariff-shifting saving: GBP 18.50
- Baseline 16:00-19:00 energy: 0.0 kWh
- Estimated starts avoided: 3573

## All-day thermostat counterfactual: same kWh, no tariff awareness

This also keeps daily kWh equal to actual, but spreads it evenly through the day to represent thermostatic maintenance that would keep cycling through 16:00-19:00.

- Baseline cost: GBP 144.28
- Baseline average unit rate: 19.31p/kWh
- Estimated tariff-shifting saving: GBP 26.27
- Baseline 16:00-19:00 energy: 93.4 kWh
- Estimated starts avoided: 3573

## Wider counterfactual: old thermostat maintained temperature every day

This estimates what would have happened if the heater kept repeating the measured baseline-day timing every day.

- Baseline energy: 1694.1 kWh
- Baseline cost: GBP 305.91
- Baseline average unit rate: 18.06p/kWh
- Estimated total saving versus actual: GBP 187.90
- Baseline 16:00-19:00 energy: 0.0 kWh
- Estimated starts avoided: 10305

## Wider all-day thermostat counterfactual

This uses the baseline day's total kWh and starts, but spreads maintenance evenly through the day, including 16:00-19:00.

- Baseline energy: 1694.1 kWh
- Baseline cost: GBP 323.13
- Baseline average unit rate: 19.07p/kWh
- Estimated total saving versus actual: GBP 205.13
- Baseline 16:00-19:00 energy: 211.8 kWh
- Estimated starts avoided: 10305

## Method notes

- Actual cost uses measured Shelly cumulative kWh deltas priced against Octopus Agile half-hour intervals.
- Implausible per-channel counter jumps above 20000W average between readings are ignored.
- Baseline timing uses the 30-minute energy distribution from the baseline date.
- The conservative model avoids claiming energy reduction; it only values moving the same kWh away from expensive periods.
- The all-day models are better for the assumption that thermostat maintenance would keep cycling through 16:00-19:00.
- The wider models include avoided kWh and should be read as thermostat-maintenance scenarios, not guaranteed bill counterfactuals.
- Daily CSV: `analysis\output_from_start\flex_savings_daily.csv`
