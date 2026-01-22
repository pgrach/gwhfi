import os
import json
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Tuya
    TUYA_ACCESS_ID = os.getenv('TUYA_ACCESS_ID')
    TUYA_ACCESS_KEY = os.getenv('TUYA_ACCESS_KEY')
    TUYA_REGION = os.getenv('TUYA_REGION', 'eu')
    TUYA_DEVICE_ID_MAIN = os.getenv('TUYA_DEVICE_ID_MAIN')
    TUYA_DEVICE_ID_MAIN = os.getenv('TUYA_DEVICE_ID_MAIN')
    TUYA_DEVICE_ID_SECOND = os.getenv('TUYA_DEVICE_ID_SECOND')

    # Shelly
    SHELLY_AUTH_KEY = os.getenv("SHELLY_CLOUD_AUTH_KEY")
    SHELLY_SERVER = os.getenv("SHELLY_CLOUD_SERVER")
    SHELLY_DEVICE_ID = os.getenv("SHELLY_DEVICE_ID")

    # Octopus
    OCTOPUS_PRODUCT_CODE = os.getenv('OCTOPUS_PRODUCT_CODE', 'AGILE-18-02-21')
    OCTOPUS_REGION_CODE = os.getenv('OCTOPUS_REGION_CODE', 'C') # Default to London (C)

    # Logic - Peak Heater (negative/free energy)
    try:
        SECOND_HEATER_THRESHOLD = float(os.getenv('SECOND_HEATER_THRESHOLD', 0.0))
    except ValueError:
        SECOND_HEATER_THRESHOLD = 0.0

    # Smart Heating Configuration
    try:
        DAILY_HEATING_BUDGET_HOURS = float(os.getenv('DAILY_HEATING_BUDGET_HOURS', 3.0))
    except ValueError:
        DAILY_HEATING_BUDGET_HOURS = 3.0

    try:
        ABSOLUTE_MAX_PRICE = float(os.getenv('ABSOLUTE_MAX_PRICE', 30.0))
    except ValueError:
        ABSOLUTE_MAX_PRICE = 30.0

    USE_BELOW_AVERAGE = os.getenv('USE_BELOW_AVERAGE', 'true').lower() == 'true'

    # Blocked hours - times when heating should NEVER occur (e.g., morning peak)
    # Format: JSON array of hours [7, 8] blocks 07:00-09:00
    try:
        BLOCKED_HOURS = json.loads(os.getenv('BLOCKED_HOURS', '[]'))
    except json.JSONDecodeError:
        BLOCKED_HOURS = []

    # Rate publication window (UTC hours) - check more frequently during this time
    RATE_PUBLISH_WINDOW_START = int(os.getenv('RATE_PUBLISH_WINDOW_START', 15))
    RATE_PUBLISH_WINDOW_END = int(os.getenv('RATE_PUBLISH_WINDOW_END', 19))

    @staticmethod
    def validate():
        missing = []
        if not Config.TUYA_ACCESS_ID: missing.append("TUYA_ACCESS_ID")
        if not Config.TUYA_ACCESS_KEY: missing.append("TUYA_ACCESS_KEY")
        if not Config.TUYA_DEVICE_ID_MAIN: missing.append("TUYA_DEVICE_ID_MAIN")
        
        if missing:
            print(f"Warning: Missing configuration for {', '.join(missing)}. Device control will fail.")
            return False
        return True
