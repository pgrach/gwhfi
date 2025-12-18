import os
import time
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("cloud_worker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load Config
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SHELLY_AUTH_KEY = os.getenv("SHELLY_CLOUD_AUTH_KEY")
SHELLY_SERVER = os.getenv("SHELLY_CLOUD_SERVER")
SHELLY_DEVICE_ID = os.getenv("SHELLY_DEVICE_ID")

# Check Config
if not all([SUPABASE_URL, SUPABASE_KEY, SHELLY_AUTH_KEY, SHELLY_SERVER, SHELLY_DEVICE_ID]):
    logger.error("Missing configuration in .env")
    exit(1)

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
        # Shelly Cloud API expects FORM data usually, or JSON? 
        # Documentation usually implies form-data for auth_key/id in POST body
        # requests.post(..., data=...) sends form-encoded
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
        return

    # Extract EMeter Data (Gen 1 usually has 'emeters' array)
    emeters = status.get("emeters", [])
    
    rows_to_insert = []
    
    for idx, emeter in enumerate(emeters):
        power = emeter.get("power", 0.0)
        voltage = emeter.get("voltage", 0.0)
        total = emeter.get("total", 0.0) # Wh
        
        row = {
            "device_id": SHELLY_DEVICE_ID,
            "channel": idx,
            "power_w": power,
            "voltage": voltage,
            "energy_total_wh": total,
            "created_at": datetime.utcnow().isoformat()
        }
        rows_to_insert.append(row)
        logger.info(f"Channel {idx}: {power}W | {voltage}V | {total}Wh")

    if rows_to_insert:
        try:
            url = f"{SUPABASE_URL}/rest/v1/energy_readings"
            response = requests.post(url, json=rows_to_insert, headers=SUPABASE_HEADERS)
            response.raise_for_status()
            logger.info(f"✅ Logged {len(rows_to_insert)} rows to Supabase.")
        except Exception as e:
            logger.error(f"❌ Supabase Insert Failed: {e}")
            if 'response' in locals():
                logger.error(f"Response: {response.text}")

if __name__ == "__main__":
    logger.info("Starting Shelly Cloud -> Supabase Worker (REST Mode)")
    
    # Run once immediately
    process_reading()
    
    # Simple loop
    while True:
        try:
            time.sleep(60) # Fetch every 60 seconds
            process_reading()
        except KeyboardInterrupt:
            logger.info("Worker stopped.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in loop: {e}")
            time.sleep(60)
