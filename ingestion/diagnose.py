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
    devices = [
        ("Main heater", Config.TUYA_DEVICE_ID_MAIN),
        ("Second heater", Config.TUYA_DEVICE_ID_SECOND),
    ]

    all_ok = True
    for name, device_id in devices:
        if not device_id:
            print_result(name, False, "device id is not configured")
            all_ok = False
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
            print_result(name, True, f"{online}, switch {state}, source {source}")
        else:
            print_result(name, False, format_tuya_failure(status))
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

    print_result("Shelly", True, ", ".join(powers))
    return True


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
