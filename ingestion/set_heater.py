import argparse

from config import Config
from services.shelly_manager import ShellyManager
from tuya_manager import TuyaManager


TUYA_HEATERS = {
    "main": ("Main/boost heater", lambda: Config.TUYA_DEVICE_ID_MAIN),
    "boost": ("Boost heater", lambda: Config.TUYA_DEVICE_ID_MAIN),
    "second": ("Second/storage heater", lambda: Config.TUYA_DEVICE_ID_SECOND),
    "storage": ("Storage heater", lambda: Config.TUYA_DEVICE_ID_SECOND),
}

SHELLY_RELAYS = {
    "shelly-main": ("Shelly main relay", lambda: Config.SHELLY_RELAY_CHANNEL_MAIN),
    "shelly-second": ("Shelly second relay", lambda: Config.SHELLY_RELAY_CHANNEL_SECOND),
}

HEATERS = {**TUYA_HEATERS, **SHELLY_RELAYS}


def parse_args():
    parser = argparse.ArgumentParser(description="Manually switch a heater or Shelly relay on or off.")
    parser.add_argument("heater", choices=HEATERS.keys())
    parser.add_argument("state", choices=["on", "off"])
    return parser.parse_args()


def main():
    args = parse_args()
    if args.heater in SHELLY_RELAYS:
        relay_name, channel_factory = SHELLY_RELAYS[args.heater]
        channel = channel_factory()
        manager = ShellyManager()
        result = manager.set_relay(channel=channel, turn_on=args.state == "on")

        if isinstance(result, dict) and result.get("success"):
            print(f"OK: {relay_name} channel {channel} turned {args.state.upper()} via Shelly Cloud.")
            return 0

        print(f"FAIL: {relay_name} channel {channel} did not turn {args.state.upper()}. Response: {result}")
        return 1

    heater_name, device_id_factory = TUYA_HEATERS[args.heater]
    device_id = device_id_factory()

    if not device_id:
        print(f"FAIL: {heater_name} device id is not configured.")
        return 1

    manager = TuyaManager()
    if args.state == "on":
        result = manager.turn_on(device_id)
    else:
        result = manager.turn_off(device_id)

    if isinstance(result, dict) and result.get("success"):
        source = result.get("source", "cloud")
        print(f"OK: {heater_name} turned {args.state.upper()} via {source}.")
        return 0

    print(f"FAIL: {heater_name} did not turn {args.state.upper()}. Response: {result}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
