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
```

If `OFF_PEAK_HEATER_TARGET=main`, the main Tuya device must be online in Tuya Cloud. If it is offline, scheduled off-peak slots cannot switch it on.

## If Heater 2 Is Physically Switched On Again

Set:

```bash
STORAGE_HEATER_ENABLED=true
OFF_PEAK_HEATER_TARGET=second
```

Then restart the Python controller.
