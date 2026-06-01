from datetime import datetime, timezone

from config import Config
from octopus_client import OctopusClient
from services.shelly_manager import ShellyManager
from services.time_service import TimeService
from tuya_manager import TuyaManager, TUYA_ACCOUNT_ERROR_CODES


def print_result(name, ok, detail):
    marker = "OK" if ok else "FAIL"
    print(f"[{marker}] {name}: {detail}")


def check_clock():
    time_service = TimeService()
    offset, safe = time_service.check_system_clock()
    if safe:
        detail = "system clock accepted"
        if offset is not None:
            detail = f"offset {offset:.3f}s"
        print_result("Clock", True, detail)
        return True

    detail = "NTP check failed"
    if offset is not None:
        detail = f"unsafe offset {offset:.3f}s"
    print_result("Clock", False, detail)
    return False


def check_octopus():
    client = OctopusClient(Config.OCTOPUS_PRODUCT_CODE, Config.OCTOPUS_REGION_CODE)
    rates = client.get_rates()
    now = datetime.now(timezone.utc)
    future_rates = [rate for rate in rates if rate['valid_to'] > now]

    if future_rates:
        first = future_rates[0]['valid_from'].isoformat()
        last = future_rates[-1]['valid_to'].isoformat()
        print_result(
            "Octopus rates",
            True,
            f"{len(future_rates)} future slots from {first} to {last}"
        )
        return True

    print_result("Octopus rates", False, f"no future slots returned from {len(rates)} total rates")
    return False


def format_tuya_failure(status):
    if not isinstance(status, dict):
        return str(status)

    code = status.get('code')
    if code is not None:
        try:
            code = int(code)
        except (TypeError, ValueError):
            pass

    account_error = TUYA_ACCOUNT_ERROR_CODES.get(code)
    if account_error:
        return f"{code} ({account_error})"

    return status.get('msg') or status.get('error') or str(status)


def check_tuya():
    manager = TuyaManager()
    print_result("Tuya control mode", True, Config.TUYA_CONTROL_MODE)
    print_result(
        "Heater control",
        True,
        f"main={Config.MAIN_HEATER_CONTROL}, second={Config.SECOND_HEATER_CONTROL}"
    )
    print_result(
        "Heater routing",
        True,
        f"storage_enabled={Config.STORAGE_HEATER_ENABLED}, off_peak_target={Config.OFF_PEAK_HEATER_TARGET}"
    )
    devices = [
        ("Main heater", Config.TUYA_DEVICE_ID_MAIN, Config.MAIN_HEATER_CONTROL == 'tuya'),
        (
            "Second heater",
            Config.TUYA_DEVICE_ID_SECOND,
            Config.SECOND_HEATER_CONTROL == 'tuya'
            and (Config.STORAGE_HEATER_ENABLED or Config.OFF_PEAK_HEATER_TARGET == 'second'),
        ),
    ]

    all_ok = True
    for name, device_id, required in devices:
        if not device_id:
            if required:
                print_result(name, False, "device id is not configured")
                all_ok = False
            else:
                print_result(name, True, "device id is not configured, not used by current routing")
            continue

        if manager.has_local_config(device_id):
            local_status = manager.get_local_status(device_id)
            if local_status and local_status.get('success'):
                state = "ON" if local_status.get('is_on') else "OFF"
                print_result(f"{name} local LAN", True, f"reachable, switch {state}")
            else:
                print_result(f"{name} local LAN", False, format_tuya_failure(local_status))
                if Config.TUYA_CONTROL_MODE == 'local':
                    all_ok = False
        elif Config.TUYA_CONTROL_MODE in {'local', 'local_then_cloud'}:
            print_result(f"{name} local LAN", False, "local key is not configured")
            if Config.TUYA_CONTROL_MODE == 'local':
                all_ok = False

        status = manager.get_status(device_id)
        if status and status.get('success'):
            state = "ON" if status.get('is_on') else "OFF"
            online = "online" if status.get('online') else "offline"
            source = status.get('source', 'cloud')
            suffix = ""
            if not required:
                suffix = ", not used by current routing"
            if status.get('online'):
                print_result(name, True, f"{online}, switch {state}, source {source}{suffix}")
            elif required:
                print_result(name, False, f"{online}, switch {state}, source {source}; configured target cannot be controlled")
                all_ok = False
            else:
                print_result(name, True, f"{online}, switch {state}, source {source}{suffix}")
        else:
            print_result(name, False, format_tuya_failure(status))
            if required:
                all_ok = False

    return all_ok


def check_shelly():
    shelly = ShellyManager()
    if not shelly.enabled:
        print_result("Shelly", False, "not configured; smart cooldown disabled")
        return False

    status = shelly.get_status()
    if not status:
        print_result("Shelly", False, "status request failed")
        return False

    emeters = status.get("emeters", [])
    if not emeters:
        print_result("Shelly", False, "no emeter channels returned")
        return False

    powers = []
    for idx, emeter in enumerate(emeters):
        powers.append(f"ch{idx}={emeter.get('power', 0.0)}W")

    relays = status.get("relays", [])
    relay_details = []
    for idx, relay in enumerate(relays):
        state = "ON" if relay.get("ison") else "OFF"
        relay_details.append(f"relay{idx}={state}")

    detail = ", ".join(powers)
    if relay_details:
        detail = f"{detail}; {', '.join(relay_details)}"

    ok = True
    required_relays = []
    if Config.MAIN_HEATER_CONTROL == 'shelly':
        required_relays.append(("main", Config.SHELLY_RELAY_CHANNEL_MAIN))
    if Config.SECOND_HEATER_CONTROL == 'shelly' and (Config.STORAGE_HEATER_ENABLED or Config.OFF_PEAK_HEATER_TARGET == 'second'):
        required_relays.append(("second", Config.SHELLY_RELAY_CHANNEL_SECOND))

    for label, channel in required_relays:
        if channel >= len(relays):
            ok = False
            detail = f"{detail}; missing Shelly relay channel {channel} for {label} heater"

    print_result("Shelly", ok, detail)
    return ok


def main():
    checks = [
        check_clock(),
        check_octopus(),
        check_tuya(),
        check_shelly(),
    ]

    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
