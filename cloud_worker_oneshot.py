import os
import requests
import logging
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Load Config from Environment (Injected by GitHub Secrets or .env)
# We don't strictly need load_dotenv if running in GH Actions, but good for local test
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SHELLY_AUTH_KEY = os.getenv("SHELLY_CLOUD_AUTH_KEY")
SHELLY_SERVER = os.getenv("SHELLY_CLOUD_SERVER")
SHELLY_DEVICE_ID = os.getenv("SHELLY_DEVICE_ID")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def get_shelly_status(device_id):
    """Fetches device status from Shelly Cloud API."""
    url = f"{SHELLY_SERVER}/device/status"
    payload = {
        "id": device_id,
        "auth_key": SHELLY_AUTH_KEY
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("isok"):
            return data.get("data", {}).get("device_status", {})
        else:
            logger.error(f"Shelly API Error: {data}")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch Shelly status: {e}")
        return None

def process_reading():
    logger.info("Fetching Shelly Cloud Status...")
    status = get_shelly_status(SHELLY_DEVICE_ID)
    
    if not status:
        logger.error("No status returned.")
        return

    emeters = status.get("emeters", [])
    rows_to_insert = []
    
    for idx, emeter in enumerate(emeters):
        row = {
            "device_id": SHELLY_DEVICE_ID,
            "channel": idx,
            "power_w": emeter.get("power", 0.0),
            "voltage": emeter.get("voltage", 0.0),
            "energy_total_wh": emeter.get("total", 0.0),
            "created_at": datetime.utcnow().isoformat()
        }
        rows_to_insert.append(row)
        logger.info(f"Channel {idx}: {row['power_w']}W | {row['energy_total_wh']}Wh")

    if rows_to_insert:
        try:
            url = f"{SUPABASE_URL}/rest/v1/energy_readings"
            response = requests.post(url, json=rows_to_insert, headers=SUPABASE_HEADERS)
            response.raise_for_status()
            logger.info(f"✅ Success! Logged {len(rows_to_insert)} rows.")
        except Exception as e:
            logger.error(f"❌ Supabase Insert Failed: {e}")

if __name__ == "__main__":
    # Just run once
    process_reading()
