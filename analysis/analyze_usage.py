import os
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Use absolute path to .env file relative to this script or current working directory
# Assuming script is run from project root or analysis/ folder
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: Missing SUPABASE_URL or SUPABASE_KEY in .env")
    exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def fetch_readings(days=30, channel=1):
    print(f"Fetching data for Channel {channel} (Last {days} days)...")
    
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    readings = []
    offset = 0
    limit = 1000
    
    while True:
        # Supabase PostgREST query with pagination
        url = f"{SUPABASE_URL}/rest/v1/energy_readings"
        params = {
            "select": "created_at,power_w,energy_total_wh",
            "channel": f"eq.{channel}",
            "created_at": f"gt.{start_date}",
            "order": "created_at.asc",
            "limit": limit,
            "offset": offset
        }
        
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            batch = response.json()
            
            if not batch:
                break
                
            readings.extend(batch)
            print(f"Fetched {len(batch)} rows (Total: {len(readings)})...")
            
            if len(batch) < limit:
                break
                
            offset += limit
            
        except Exception as e:
            print(f"Error fetching data batch: {e}")
            break
            
    return readings

def analyze_data(readings):
    if not readings:
        print("No readings found.")
        return

    print(f"Analyzing {len(readings)} data points...")
    
    # Group by Day
    daily_stats = {}
    
    for r in readings:
        dt = datetime.fromisoformat(r['created_at'])
        day_key = dt.strftime('%Y-%m-%d')
        
        if day_key not in daily_stats:
            daily_stats[day_key] = {
                'readings': [],
                'total_wh_start': None,
                'total_wh_end': None
            }
            
        daily_stats[day_key]['readings'].append(r)
        
        # Track min/max energy counter for the day
        wh = r['energy_total_wh']
        if wh > 0: # Filter invalid 0s if any
            stats = daily_stats[day_key]
            if stats['total_wh_start'] is None or wh < stats['total_wh_start']:
                stats['total_wh_start'] = wh
            if stats['total_wh_end'] is None or wh > stats['total_wh_end']:
                stats['total_wh_end'] = wh

    # Calculate Metrics per Day
    total_kwh_sum = 0
    total_on_minutes_sum = 0
    total_solid_block_minutes_sum = 0
    valid_days = 0
    
    # Redirect output to file
    with open("analysis_report.txt", "w") as f:
        f.write("\n--- Daily Breakdown ---\n")
        f.write(f"{'Date':<12} | {'kWh':<8} | {'On Time (h)':<12} | {'Solid Burn (h)':<14} | {'Notes'}\n")
        f.write("-" * 70 + "\n")
        
        sorted_days = sorted(daily_stats.keys())
        
        for day in sorted_days:
            stats = daily_stats[day]
            data_points = stats['readings']
            
            # Consumption (kWh)
            if stats['total_wh_start'] is not None and stats['total_wh_end'] is not None:
                day_kwh = (stats['total_wh_end'] - stats['total_wh_start']) / 1000.0
            else:
                day_kwh = 0.0
                
            # Analysis of "ON" time
            # We assume ~1 minute intervals
            on_minutes = 0
            solid_block_minutes = 0
            
            current_block_duration = 0
            
            for r in data_points:
                power = r['power_w']
                
                if power > 100: # Heater ON threshold
                    on_minutes += 1
                    
                    if power > 2000: # High power "Solid" heating
                        current_block_duration += 1
                    else:
                        # If high power drops, was it a solid block?
                        # Let's count it if it was sustained
                        if current_block_duration > 0:
                            solid_block_minutes += current_block_duration
                            current_block_duration = 0
                else:
                    # Heater OFF
                    if current_block_duration > 0:
                        solid_block_minutes += current_block_duration
                        current_block_duration = 0
                        
            # Add stragglers
            solid_block_minutes += current_block_duration
            
            # Normalize to hours
            on_hours = on_minutes / 60.0
            solid_hours = solid_block_minutes / 60.0
            
            # Filter incomplete days (very low data points)
            if len(data_points) < 60:
                f.write(f"{day:<12} | {day_kwh:.2f}     | (Insufficient Data)    |\n")
                continue
                
            valid_days += 1
            total_kwh_sum += day_kwh
            total_on_minutes_sum += on_minutes
            total_solid_block_minutes_sum += solid_block_minutes
            
            note = ""
            if on_hours > 5: note = "Heavy Usage"
            
            f.write(f"{day:<12} | {day_kwh:.2f}     | {on_hours:.2f}         | {solid_hours:.2f}           | {note}\n")

        if valid_days == 0:
            f.write("\nNo valid days found.\n")
            return

        # Averages
        avg_kwh = total_kwh_sum / valid_days
        avg_on_hours = (total_on_minutes_sum / valid_days) / 60.0
        avg_solid_hours = (total_solid_block_minutes_sum / valid_days) / 60.0
        
        f.write("\n--- Summary (Last 30 Days) ---\n")
        f.write(f"Average Consumption:  {avg_kwh:.2f} kWh / day\n")
        f.write(f"Average Total ON Time: {avg_on_hours:.2f} hours / day\n")
        f.write(f"Average 'Full Power':  {avg_solid_hours:.2f} hours / day (Initial Heating)\n")
        f.write(f"Average 'Maintaining': {avg_on_hours - avg_solid_hours:.2f} hours / day (Cycling/Barcode)\n")
        
        f.write(f"\nRecommendation:\n")
        f.write(f"Based on the 'Full Power' time, your tank takes about {avg_solid_hours:.2f} hours to heat from cold.\n")
        f.write(f"The 'Maintaining' time shows it runs for another {avg_on_hours - avg_solid_hours:.2f} hours just pulsing.\n")
        f.write(f"A fixed window of {avg_solid_hours + 0.5:.1f} to {avg_solid_hours + 1:.1f} hours should be sufficient.\n")
    
    print("Analysis complete. Saved to analysis_report.txt")

if __name__ == "__main__":
    channel_id = 1 # Off-Peak Heater
    data = fetch_readings(days=30, channel=channel_id)
    analyze_data(data)
