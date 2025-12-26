import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}
from datetime import datetime, timedelta

# Count all rows for last 7 days
today = datetime.utcnow()
seven_days_ago = today - timedelta(days=7)
start_iso = seven_days_ago.isoformat()

print(f"Checking data since {start_iso}")

url = f"{SUPABASE_URL}/rest/v1/energy_readings?select=created_at&created_at=gte.{start_iso}&limit=1"
r = requests.head(url, headers={**headers, "Prefer": "count=exact"})
range_header = r.headers.get("Content-Range", "0-0/0")
total = range_header.split('/')[-1] if '/' in range_header else "0"

print(f"Total rows in last 7 days: {total}")

results = {"total_7d": total}
with open("results_7d.json", "w") as f:
    json.dump(results, f, indent=2)


