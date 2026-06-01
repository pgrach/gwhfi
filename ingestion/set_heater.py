import argparse

from config import Config
from tuya_manager import TuyaManager


HEATERS = {
    "boost": ("Boost heater", lambda: Config.TUYA_DEVICE_ID_MAIN),
    "storage": ("Storage heater", lambda: Config.TUYA_DEVICE_ID_SECOND),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Manually switch a heater on or off via the configured Tuya control path.")
    parser.add_argument("heater", choices=HEATERS.keys())
    parser.add_argument("state", choices=["on", "off"])
    return parser.parse_args()


def main():
    args = parse_args()
    heater_name, device_id_factory = HEATERS[args.heater]
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
