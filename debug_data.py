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

# Fetch readings from today
url = f"{SUPABASE_URL}/rest/v1/energy_readings?select=created_at,energy_total_wh,channel&order=created_at.desc&limit=100"

resp = requests.get(url, headers=headers)
data = resp.json()

print(f"Fetched {len(data)} rows.")
for row in data[:20]:
    print(f"Time: {row['created_at']} | Channel: {row['channel']} | TotalWh: {row['energy_total_wh']}")
