import os
import requests
import json
from dotenv import load_dotenv

# Load env from .env file
load_dotenv()

SERVER = os.getenv("SHELLY_CLOUD_SERVER")
AUTH_KEY = os.getenv("SHELLY_CLOUD_AUTH_KEY")
DEVICE_ID = os.getenv("SHELLY_DEVICE_ID")

if not all([SERVER, AUTH_KEY, DEVICE_ID]):
    print("Missing SHELLY configuration in .env")
    exit(1)

print(f"Targeting Server: {SERVER}")
print(f"Device ID: {DEVICE_ID}")

def try_endpoint(name, url, payload):
    print(f"\nScanning: {name}")
    print(f"POST {url}")
    try:
        response = requests.post(url, data=payload, timeout=10)
        print(f"Status: {response.status_code}")
        try:
            data = response.json()
            # print(json.dumps(data, indent=2))
            if data.get("isok"):
                print("✅ RESULT: SUCCESS")
                print(str(data)[:200] + "...")
                return True
            else:
                print("❌ RESULT: FAILED (API Error)")
                print(data)
        except:
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ RESULT: FAILED (Exception: {e})")
    return False

# 1. Standard Status (Baseline)
try_endpoint("Baseline Status", f"{SERVER}/device/status", {"id": DEVICE_ID, "auth_key": AUTH_KEY})

# 2. Undocumented Statistics (EM-3P style - often works for EM too?)
# Try various time ranges
import datetime
today = datetime.datetime.now().strftime("%Y-%m-%d")

# Attempts based on search results
endpoints = [
    # Attempt 1: v2 statistics for 3-phase (sometimes works for 1-phase)
    # date_from/to format is usually YYYY-MM-DD or similar
    (f"{SERVER}/v2/statistics/power-consumption/em-3p", {
        "id": DEVICE_ID, 
        "auth_key": AUTH_KEY, 
        "date_range": "day", 
        "date": today
    }),
    # Attempt 2: em-1p ?
    (f"{SERVER}/v2/statistics/power-consumption/em-1p", {
        "id": DEVICE_ID, 
        "auth_key": AUTH_KEY, 
        "date_range": "day", 
        "date": today
    }),
    # Attempt 3: relay consumption
    (f"{SERVER}/statistics/relay/consumption", {
        "id": DEVICE_ID, 
        "auth_key": AUTH_KEY, 
        "date_range": "day", 
        "date": today,
        "channel": 0
    }),
     # Attempt 4: consumption (generic)
    (f"{SERVER}/device/consumption", {
        "id": DEVICE_ID, 
        "auth_key": AUTH_KEY, 
        "date_range": "day", 
        "date": today
    })
]

for url, data in endpoints:
    try_endpoint(url.split("/")[-1], url, data)
