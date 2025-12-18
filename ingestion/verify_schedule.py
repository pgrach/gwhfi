import sys
import os
import logging
from datetime import datetime

# Add current dir to path
sys.path.append(os.path.join(os.getcwd(), 'ingestion'))

from config import Config
from octopus_client import OctopusClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify():
    print("--- Verifying Smart Daily Slots ---")
    
    # Initialize Client
    client = OctopusClient(Config.OCTOPUS_PRODUCT_CODE, Config.OCTOPUS_REGION_CODE)
    
    # Fetch rates
    print("Fetching rates...")
    rates = client.get_rates()
    print(f"Fetched {len(rates)} rates.")
    
    if not rates:
        print("Error: No rates fetched.")
        return

    # Run Smart Analysis
    print("\nRunning find_smart_daily_slots()...")
    smart_slots = client.find_smart_daily_slots(rates)
    
    print(f"\nTotal Smart Slots Selected: {len(smart_slots)}")
    
    # Group by day for checking
    by_day = {}
    for s in smart_slots:
        d = s['valid_from'].date()
        if d not in by_day: by_day[d] = []
        by_day[d].append(s)
        
    for day, slots in by_day.items():
        print(f"\nDay: {day}")
        print(f"  Slots Selected: {len(slots)}")
        if slots:
            avg_selected = sum(s['value_inc_vat'] for s in slots) / len(slots)
            print(f"  Avg Price of Selected: {avg_selected:.2f}p")
            print(f"  First Slot: {slots[0]['valid_from'].time()} ({slots[0]['value_inc_vat']}p)")
            print(f"  Last Slot:  {slots[-1]['valid_from'].time()} ({slots[-1]['value_inc_vat']}p)")

if __name__ == "__main__":
    verify()
