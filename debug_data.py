import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timedelta

load_dotenv(dotenv_path=".env.local")

url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not url or not key:
    print("Missing env vars")
    exit()

supabase = create_client(url, key)

# Fetch last 12 hours
now = datetime.utcnow()
start = now - timedelta(hours=12)

with open("debug_output.txt", "w", encoding="utf-8") as f:
    f.write(f"Fetching data since {start.isoformat()}...\n")

    response = supabase.table("energy_readings") \
        .select("created_at, channel, power_w") \
        .gte("created_at", start.isoformat()) \
        .order("created_at", desc=True) \
        .execute()

    data = response.data
    f.write(f"Found {len(data)} readings.\n")

    # Group by time slots to see if we have 30-min blocks
    last_state = {}
    f.write("\n--- State Transitions ---\n")
    for r in reversed(data): # Process chronologically
        ch = r['channel']
        p = r['power_w']
        t = r['created_at']
        
        state = "ON" if p > 100 else "OFF"
        
        if ch not in last_state:
            last_state[ch] = state
            f.write(f"[{t}] Ch {ch} initialized: {state} ({p}W)\n")
        
        if last_state[ch] != state:
            f.write(f"[{t}] Ch {ch} switched {last_state[ch]} -> {state} ({p}W)\n")
            last_state[ch] = state

    f.write("\n--- Sample Raw Data (Last 10 mins) ---\n")
    for r in data[:10]:
         f.write(f"[{r['created_at']}] Ch {r['channel']}: {r['power_w']} W\n")
