import os
import json
from dotenv import load_dotenv

load_dotenv()


def int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def clamped_int_env(name, default, minimum, maximum):
    """Parse an integer environment variable and constrain it to a safe range."""
    value = int_env(name, default)
    return max(minimum, min(maximum, value))


def blocked_hours_env(name, default):
    """Parse blocked hours, restoring safe defaults for any malformed value."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return list(default)

    try:
        hours = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return list(default)

    if not isinstance(hours, list):
        return list(default)
    if any(type(hour) is not int or not 0 <= hour <= 23 for hour in hours):
        return list(default)
    return hours


def bool_env(name, default):
    """Parse a boolean environment variable, falling back safely on invalid input."""
    value = os.getenv(name)
    if value is None:
        return bool(default)

    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    return bool(default)


class Config:
    # Safety interlock: commands are simulated unless live control is explicitly enabled.
    DRY_RUN = bool_env('DRY_RUN', True)

    # Tuya
    TUYA_ACCESS_ID = os.getenv('TUYA_ACCESS_ID')
    TUYA_ACCESS_KEY = os.getenv('TUYA_ACCESS_KEY')
    TUYA_REGION = os.getenv('TUYA_REGION', 'eu')
    TUYA_DEVICE_ID_MAIN = os.getenv('TUYA_DEVICE_ID_MAIN')
    TUYA_DEVICE_ID_SECOND = os.getenv('TUYA_DEVICE_ID_SECOND')
    TUYA_CONTROL_MODE = os.getenv('TUYA_CONTROL_MODE', 'cloud').lower()  # cloud, local, local_then_cloud
    TUYA_DEVICE_IP_MAIN = os.getenv('TUYA_DEVICE_IP_MAIN', 'Auto')
    TUYA_DEVICE_IP_SECOND = os.getenv('TUYA_DEVICE_IP_SECOND', 'Auto')
    TUYA_LOCAL_KEY_MAIN = os.getenv('TUYA_LOCAL_KEY_MAIN')
    TUYA_LOCAL_KEY_SECOND = os.getenv('TUYA_LOCAL_KEY_SECOND')
    STORAGE_HEATER_ENABLED = os.getenv('STORAGE_HEATER_ENABLED', 'true').lower() == 'true'
    OFF_PEAK_HEATER_TARGET = os.getenv(
        'OFF_PEAK_HEATER_TARGET',
        'second' if STORAGE_HEATER_ENABLED else 'main'
    ).lower()

    if OFF_PEAK_HEATER_TARGET not in {'main', 'second'}:
        OFF_PEAK_HEATER_TARGET = 'main'

    try:
        TUYA_PROTOCOL_VERSION_MAIN = float(os.getenv('TUYA_PROTOCOL_VERSION_MAIN', 3.3))
    except ValueError:
        TUYA_PROTOCOL_VERSION_MAIN = 3.3

    try:
        TUYA_PROTOCOL_VERSION_SECOND = float(os.getenv('TUYA_PROTOCOL_VERSION_SECOND', 3.3))
    except ValueError:
        TUYA_PROTOCOL_VERSION_SECOND = 3.3

    try:
        TUYA_LOCAL_DPS_MAIN = int(os.getenv('TUYA_LOCAL_DPS_MAIN', 1))
    except ValueError:
        TUYA_LOCAL_DPS_MAIN = 1

    try:
        TUYA_LOCAL_DPS_SECOND = int(os.getenv('TUYA_LOCAL_DPS_SECOND', 1))
    except ValueError:
        TUYA_LOCAL_DPS_SECOND = 1

    # Shelly
    SHELLY_AUTH_KEY = os.getenv("SHELLY_CLOUD_AUTH_KEY")
    SHELLY_SERVER = os.getenv("SHELLY_CLOUD_SERVER")
    # Keep the existing meter separate from the Pro 1 relay. SHELLY_DEVICE_ID
    # remains as a backwards-compatible alias for the existing energy meter.
    SHELLY_DEVICE_ID = os.getenv("SHELLY_DEVICE_ID")
    SHELLY_METER_DEVICE_ID = os.getenv("SHELLY_METER_DEVICE_ID") or SHELLY_DEVICE_ID
    SHELLY_RELAY_DEVICE_ID = os.getenv("SHELLY_RELAY_DEVICE_ID")
    SHELLY_CHANNEL_MAIN = int_env("SHELLY_CHANNEL_MAIN", 0)
    SHELLY_CHANNEL_SECOND = int_env("SHELLY_CHANNEL_SECOND", 1)
    SHELLY_RELAY_CHANNEL_MAIN = int_env("SHELLY_RELAY_CHANNEL_MAIN", os.getenv("SHELLY_RELAY_CHANNEL", 0))
    SHELLY_RELAY_CHANNEL_SECOND = int_env("SHELLY_RELAY_CHANNEL_SECOND", os.getenv("SHELLY_RELAY_CHANNEL", 0))
    SHELLY_CONTROL_LEASE_DEFAULT_SECONDS = 180
    SHELLY_CONTROL_LEASE_MIN_SECONDS = 120
    SHELLY_CONTROL_LEASE_MAX_SECONDS = 300
    SHELLY_CONTROL_LEASE_SECONDS = clamped_int_env(
        "SHELLY_CONTROL_LEASE_SECONDS",
        SHELLY_CONTROL_LEASE_DEFAULT_SECONDS,
        SHELLY_CONTROL_LEASE_MIN_SECONDS,
        SHELLY_CONTROL_LEASE_MAX_SECONDS,
    )

    # Octopus
    OCTOPUS_PRODUCT_CODE = os.getenv('OCTOPUS_PRODUCT_CODE', 'AGILE-24-10-01')
    OCTOPUS_REGION_CODE = os.getenv('OCTOPUS_REGION_CODE', 'C') # Default to London (C)
    LOCAL_TIMEZONE = os.getenv('LOCAL_TIMEZONE', 'Europe/London')

    # Logic - Peak Heater (negative/free energy)
    try:
        SECOND_HEATER_THRESHOLD = float(os.getenv('SECOND_HEATER_THRESHOLD', 0.0))
    except ValueError:
        SECOND_HEATER_THRESHOLD = 0.0

    # Smart Heating Configuration
    try:
        DAILY_HEATING_BUDGET_HOURS = float(os.getenv('DAILY_HEATING_BUDGET_HOURS', 5.0))
    except ValueError:
        DAILY_HEATING_BUDGET_HOURS = 3.0

    try:
        ABSOLUTE_MAX_PRICE = float(os.getenv('ABSOLUTE_MAX_PRICE', 30.0))
    except ValueError:
        ABSOLUTE_MAX_PRICE = 30.0

    USE_BELOW_AVERAGE = os.getenv('USE_BELOW_AVERAGE', 'true').lower() == 'true'
    SMART_COOLDOWN_ENABLED = os.getenv('SMART_COOLDOWN_ENABLED', 'false').lower() == 'true'

    MAIN_HEATER_CONTROL = os.getenv('MAIN_HEATER_CONTROL', 'tuya').lower()
    SECOND_HEATER_CONTROL = os.getenv('SECOND_HEATER_CONTROL', 'tuya').lower()

    if MAIN_HEATER_CONTROL not in {'tuya', 'shelly'}:
        MAIN_HEATER_CONTROL = 'tuya'

    if SECOND_HEATER_CONTROL not in {'tuya', 'shelly'}:
        SECOND_HEATER_CONTROL = 'tuya'

    @staticmethod
    def validate_shelly_control_routing():
        """A single configured Shelly relay must not receive two heater policies."""
        return not (
            Config.MAIN_HEATER_CONTROL == 'shelly'
            and Config.SECOND_HEATER_CONTROL == 'shelly'
        )

    # Blocked hours - times when heating should NEVER occur (e.g., morning peak)
    # Format: JSON array of hours [7, 8] blocks 07:00-09:00
    SAFE_BLOCKED_HOURS = [7, 8, 16, 17, 18]
    BLOCKED_HOURS = blocked_hours_env('BLOCKED_HOURS', SAFE_BLOCKED_HOURS)

    # Rate publication window (UTC hours) - check more frequently during this time
    RATE_PUBLISH_WINDOW_START = int(os.getenv('RATE_PUBLISH_WINDOW_START', 15))
    RATE_PUBLISH_WINDOW_END = int(os.getenv('RATE_PUBLISH_WINDOW_END', 19))

    @staticmethod
    def validate_cloud():
        missing = []
        if not Config.TUYA_ACCESS_ID: missing.append("TUYA_ACCESS_ID")
        if not Config.TUYA_ACCESS_KEY: missing.append("TUYA_ACCESS_KEY")
        if not Config.TUYA_DEVICE_ID_MAIN: missing.append("TUYA_DEVICE_ID_MAIN")

        if missing:
            print(f"Warning: Missing cloud configuration for {', '.join(missing)}.")
            return False
        return True

    @staticmethod
    def validate_local(device_id=None):
        missing = []
        if not Config.TUYA_DEVICE_ID_MAIN:
            missing.append("TUYA_DEVICE_ID_MAIN")

        if device_id == Config.TUYA_DEVICE_ID_SECOND:
            if not Config.TUYA_DEVICE_ID_SECOND:
                missing.append("TUYA_DEVICE_ID_SECOND")
            if not Config.TUYA_LOCAL_KEY_SECOND:
                missing.append("TUYA_LOCAL_KEY_SECOND")
        elif not Config.TUYA_LOCAL_KEY_MAIN:
            missing.append("TUYA_LOCAL_KEY_MAIN")

        if missing:
            print(f"Warning: Missing local Tuya configuration for {', '.join(missing)}.")
            return False
        return True

    @staticmethod
    def validate():
        if Config.TUYA_CONTROL_MODE == 'local':
            return Config.validate_local()
        return Config.validate_cloud()
