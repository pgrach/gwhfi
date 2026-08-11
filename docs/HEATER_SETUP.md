# Heater Setup Notes

This installation should run scheduled off-peak heating on the lower/storage heater.

## Desired Physical State

- Heater 1 / Main / Boost is the blue channel (`channel 0`).
- Heater 2 / Storage / Lower heater is the green channel (`channel 1`).
- Scheduled off-peak slots should turn on Heater 2 / Storage / Lower heater, so the green line should show power during those slots.
- If Heater 2 is physically switched off at the wall, Tuya can still report its smart switch as ON while Shelly reads 0W. In that case the scheduler is asking for heat, but the lower heater is blocked downstream.

## Controller Defaults

The controller defaults are set for the lower/storage heater:

```bash
DRY_RUN=true
STORAGE_HEATER_ENABLED=true
OFF_PEAK_HEATER_TARGET=second
SMART_COOLDOWN_ENABLED=false
TUYA_CONTROL_MODE=cloud
MAIN_HEATER_CONTROL=tuya
SECOND_HEATER_CONTROL=tuya
```

With these defaults:

- Heater commands are logged but not sent. Live control requires an explicit `DRY_RUN=false` after commissioning checks pass.
- Off-peak scheduled slots drive Heater 2 / Storage / Lower heater (`channel 1`, green).
- Peak/free-energy slots can still drive Heater 1 / Boost (`channel 0`, blue).
- Smart cooldown is off by default so low/zero Shelly readings do not silently cancel an active scheduled slot.

## Railway State

Railway currently has Tuya Cloud credentials (`TUYA_ACCESS_ID`, `TUYA_ACCESS_KEY`, `TUYA_DEVICE_ID_MAIN`, `TUYA_DEVICE_ID_SECOND`) but no local Tuya keys. That means the live automation uses Tuya Cloud, not local LAN control.

Recommended Railway variables for the normal lower-heater setup:

```bash
STORAGE_HEATER_ENABLED=true
OFF_PEAK_HEATER_TARGET=second
SMART_COOLDOWN_ENABLED=false
TUYA_CONTROL_MODE=cloud
MAIN_HEATER_CONTROL=tuya
SECOND_HEATER_CONTROL=tuya
```

If these variables are omitted, the code defaults to the same lower-heater routing.

## Diagnosis From 2026-06-01

- The configured second/storage Tuya device is named `Offpeak_keepon`, is online, and accepts control.
- Channel 1 / green last drew real lower-heater power on 2026-05-29 at 00:13 UTC.
- Scheduled slots continued after that date, so the scheduler did not stop making slots.
- If green remains at 0W during scheduled slots, check the lower heater's physical wall switch, timer, thermostat, fuse, contactor, or the heater itself.
- The configured main/boost Tuya device is named `Peak_keepoff` and was offline in Tuya Cloud during diagnosis. A direct ON command returned `result=false`, so Tuya Cloud could not switch it at that time.

## Shelly Pro 1 Relay Control

The off-peak schedule can control a dedicated Shelly Pro 1 instead of the
previous Tuya storage-heater switch. Keep its device ID separate from the
Shelly energy meter used for dashboard telemetry:

```bash
OFF_PEAK_HEATER_TARGET=second
SECOND_HEATER_CONTROL=shelly
SHELLY_RELAY_DEVICE_ID=00700741fa34
SHELLY_RELAY_CHANNEL_SECOND=0
SHELLY_CONTROL_LEASE_SECONDS=180
```

The controller renews a short ON lease every minute. If the controller,
Railway, or Shelly Cloud disappears, the device automatically returns OFF when
the lease expires. The Pro 1 must be added to the same Shelly Cloud account,
and Railway must receive `SHELLY_CLOUD_SERVER` and `SHELLY_CLOUD_AUTH_KEY` as
secrets.

This must only be enabled after relay channel 0 is verified to switch the
off-peak heater or its contactor. The Pro 1 reports relay position but does not
measure heater power; the separate Shelly energy meter remains the source for
green-channel consumption.

Manual tests:

These commands honor `DRY_RUN`. Keep it enabled until commissioning is
approved; live Shelly ON tests always include the bounded auto-OFF lease.

```bash
python ingestion/set_heater.py storage on
python ingestion/set_heater.py storage off
python ingestion/set_heater.py shelly-second on
python ingestion/set_heater.py shelly-second off
```
