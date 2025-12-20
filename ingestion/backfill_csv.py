import os
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SHELLY_DEVICE_ID = os.getenv("SHELLY_DEVICE_ID")

if not all([SUPABASE_URL, SUPABASE_KEY, SHELLY_DEVICE_ID]):
    print("Missing Configuration")
    exit(1)

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

# Data provided by user
# Format: Date Time \t Wh
raw_data = """
19/12/2025 15:00 	0
19/12/2025 16:00 	0
19/12/2025 17:00 	0
19/12/2025 18:00 	0
19/12/2025 19:00 	0
19/12/2025 20:00 	0
19/12/2025 21:00 	0
19/12/2025 22:00 	0
19/12/2025 23:00 	0
20/12/2025 00:00 	0
20/12/2025 01:00 	460.31
20/12/2025 02:00 	288.52
20/12/2025 03:00 	158.72
20/12/2025 04:00 	115.21
20/12/2025 05:00 	243.52
20/12/2025 06:00 	0
20/12/2025 07:00 	0
20/12/2025 08:00 	0
20/12/2025 09:00 	0
20/12/2025 10:00 	0
20/12/2025 11:00 	227.1
20/12/2025 12:00 	150.1
20/12/2025 13:00 	106.33
20/12/2025 14:00 	0
"""

def parse_and_upload():
    print("Starting Backfill...")
    count = 0
    
    # Assume Channel 1 (Off-Peak) based on "Night" context. 
    # Change to 0 if needed (Peak).
    # The screenshot shows "Smart water" consumption and lots of activity 01:00-05:00
    # which matches typical Off-Peak / Night Rate usage.
    CHANNEL = 1 
    
    lines = raw_data.strip().split('\n')
    rows_to_insert = []
    
    for line in lines:
        parts = line.strip().split('\t')
        if len(parts) < 2: 
            # Try splitting by multiple spaces if tab fails
            parts = line.strip().split()
            if len(parts) < 3: continue # Date Time Value
            # Reconstruct
            date_str = parts[0]
            time_str = parts[1]
            val_str = parts[2]
        else:
            date_time_str = parts[0].strip()
            val_str = parts[1].strip()
            # Split date/time
            dt_parts = date_time_str.split(' ')
            date_str = dt_parts[0]
            time_str = dt_parts[1]
            
        try:
            # Parse Date: 19/12/2025 15:00
            # Needs to be ISO format for Supabase
            dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            
            # Simulation Logic:
            # Heater is 3000W constant.
            # On-Time (minutes) = (Wh / 3000) * 60
            consumption_wh = float(val_str)
            
            if consumption_wh > 0:
                minutes_on = (consumption_wh / 3000.0) * 60
                
                # Check for sanity (cant range > 60 mins in a 1 hour slot basically)
                if minutes_on > 59: minutes_on = 59
                
                # Point 1: Turn ON (3000 W) at start of hour
                row_on = {
                    "device_id": SHELLY_DEVICE_ID,
                    "channel": CHANNEL,
                    "power_w": 3000.0, 
                    "voltage": 230.0,
                    "energy_total_wh": 0.0, # Placeholder
                    "created_at": dt.isoformat()
                }
                rows_to_insert.append(row_on)
                
                # Point 2: Turn OFF (0 W) after 'minutes_on'
                dt_off = dt + datetime.timedelta(minutes=minutes_on)
                row_off = {
                    "device_id": SHELLY_DEVICE_ID,
                    "channel": CHANNEL,
                    "power_w": 0.0,
                    "voltage": 230.0,
                    "energy_total_wh": 0.0,
                    "created_at": dt_off.isoformat()
                }
                rows_to_insert.append(row_off)
                
                count += 1
                print(f"Parsed: {dt.strftime('%H:%M')} | {consumption_wh}Wh -> {minutes_on:.1f} min ON")
            else:
                 # It was 0, so just ensure it's recorded as 0
                 row = {
                    "device_id": SHELLY_DEVICE_ID,
                    "channel": CHANNEL,
                    "power_w": 0.0,
                    "voltage": 230.0,
                    "energy_total_wh": 0.0,
                    "created_at": dt.isoformat()
                }
                 rows_to_insert.append(row)

        except ValueError as e:
            print(f"Skipping line '{line}': {e}")
            
    if rows_to_insert:
        # First, DELETE existing backfill for this range to avoid duplicates/mess
        # We identify backfill rows by energy_total_wh = 0 (and assumed channel)
        # Or just by date range? Date range is safer.
        print("Cleaning up old backfill data...")
        start_cleanup = "2025-12-19T15:00:00"
        end_cleanup = "2025-12-20T14:00:00"
        
        del_url = f"{SUPABASE_URL}/rest/v1/energy_readings?energy_total_wh=eq.0&created_at=gte.{start_cleanup}&created_at=lte.{end_cleanup}"
        requests.delete(del_url, headers=SUPABASE_HEADERS)

        print(f"Uploading {len(rows_to_insert)} simulation rows...")
        url = f"{SUPABASE_URL}/rest/v1/energy_readings"
        resp = requests.post(url, json=rows_to_insert, headers=SUPABASE_HEADERS)
        if resp.status_code in [200, 201]:
            print("✅ Upload Complete!")
        else:
            print(f"❌ Upload Failed: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    parse_and_upload()
