# Heater Setup Notes

This installation normally runs as a one-heater setup.

## Physical State

- Heater 1 / Main / Boost is the heater normally used.
- Heater 2 / Storage is usually physically switched off at the wall switch.
- Because Heater 2 is physically switched off, Tuya can report its smart switch as ON while Shelly still reads 0W. That is expected and does not mean the scheduler failed.

## Controller Defaults

The controller defaults are set for this one-heater setup:

```bash
STORAGE_HEATER_ENABLED=false
OFF_PEAK_HEATER_TARGET=main
SMART_COOLDOWN_ENABLED=false
TUYA_CONTROL_MODE=cloud
```

With these defaults, off-peak scheduled slots drive the main heater. Heater 2 is not used unless it is physically switched on and `STORAGE_HEATER_ENABLED=true` is set.

## Railway State

Railway currently has Tuya Cloud credentials (`TUYA_ACCESS_ID`, `TUYA_ACCESS_KEY`, `TUYA_DEVICE_ID_MAIN`, `TUYA_DEVICE_ID_SECOND`) but no local Tuya keys. That means the live automation uses Tuya Cloud, not local LAN control.

Recommended Railway variables for the normal one-heater setup:

```bash
STORAGE_HEATER_ENABLED=false
OFF_PEAK_HEATER_TARGET=main
SMART_COOLDOWN_ENABLED=false
TUYA_CONTROL_MODE=cloud
MAIN_HEATER_CONTROL=tuya
SECOND_HEATER_CONTROL=tuya
```

If `OFF_PEAK_HEATER_TARGET=main`, the main Tuya device must be online in Tuya Cloud. If it is offline, scheduled off-peak slots cannot switch it on.

## Current Live Diagnosis

Checked on 2026-06-01:

- The configured main/boost Tuya device is named `Peak_keepoff` in Tuya Cloud and is offline. A direct ON command returned `result=false`, so Tuya Cloud cannot currently switch it on.
- The configured second/storage Tuya device is named `Offpeak_keepon`, is online, and reports switch ON. Because Heater 2 is physically switched off at the wall, Shelly still reads 0W even when this Tuya switch is ON.
- Shelly Cloud is reachable. It exposes power channels `ch0` and `ch1` plus one relay (`relay0`), and `relay0` currently reports ON.

With the normal one-heater routing (`OFF_PEAK_HEATER_TARGET=main`), the blocker is therefore the main Tuya device being offline. With the old routing (`OFF_PEAK_HEATER_TARGET=second`), the blocker is the physical Heater 2 wall switch being off.

## Shelly Relay Control

The controller can optionally use the Shelly relay instead of Tuya for the main heater:

```bash
MAIN_HEATER_CONTROL=shelly
SHELLY_RELAY_CHANNEL_MAIN=0
```

This only helps if Shelly relay channel 0 is physically wired to switch the usable heater or its contactor. The relay currently reports ON while both Shelly power channels read 0W, so enabling Shelly control alone may not create heat if the heater is blocked by a wall switch, timer, thermostat, or another downstream control.

Manual Shelly relay test:

```bash
python ingestion/set_heater.py shelly-main on
python ingestion/set_heater.py shelly-main off
```

## If Heater 2 Is Physically Switched On Again

Set:

```bash
STORAGE_HEATER_ENABLED=true
OFF_PEAK_HEATER_TARGET=second
```

Then restart the Python controller.
