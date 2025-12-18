import requests
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OctopusClient:
    BASE_URL = "https://api.octopus.energy/v1/products"

    def __init__(self, product_code, region_code):
        self.product_code = product_code
        self.region_code = region_code

    def get_rates(self, period_from=None, period_to=None):
        """
        Fetch rates for the specified period.
        If no period specified, fetches for now until next 24h (approx).
        """
        url = f"{self.BASE_URL}/{self.product_code}/electricity-tariffs/E-1R-{self.product_code}-{self.region_code}/standard-unit-rates/"
        
        params = {}
        if period_from:
            params['period_from'] = period_from
        if period_to:
            params['period_to'] = period_to
            
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Results are usually paginated, but for 24h chunks usually fits in one. 
            # For robustness, we could handle pagination, but let's start simple.
            results = data.get('results', [])
            
            # Parse dates and sort by valid_from
            formatted_rates = []
            for r in results:
                formatted_rates.append({
                    'value_inc_vat': r['value_inc_vat'],
                    'valid_from': datetime.fromisoformat(r['valid_from'].replace('Z', '+00:00')),
                    'valid_to': datetime.fromisoformat(r['valid_to'].replace('Z', '+00:00'))
                })
            
            # Sort by time
            formatted_rates.sort(key=lambda x: x['valid_from'])
            return formatted_rates

        except requests.RequestException as e:
            logger.error(f"Error fetching rates from Octopus: {e}")
            return []

    def find_cheapest_blocks(self, rates, hours_needed):
        """
        Finds the cheapest contiguous or non-contiguous blocks of time.
        For water heating, we generally want the absolute cheapest 30-min slots, 
        they don't strictly need to be contiguous, but contiguous is better for the heater.
        
        However, the user asked for "cheapest periods", usually implying the lowest cost slots.
        Agile slots are 30 mins.
        """
        slots_needed = int(hours_needed * 2) # 30 min slots
        
        if len(rates) < slots_needed:
            logger.warning("Not enough rate data to find required slots.")
            return rates # Return all available if less than needed? Or empty?
        
        # Sort by price
        sorted_rates = sorted(rates, key=lambda x: x['value_inc_vat'])
        
        # Pick the cheapest N slots
        cheapest_slots = sorted_rates[:slots_needed]
        
        # Sort them back by time so we can see the schedule chronologically
        cheapest_slots.sort(key=lambda x: x['valid_from'])
        
        return cheapest_slots

    def get_negative_rates(self, rates, threshold=0.0):
        """
        Returns all slots where price is <= threshold.
        """
        return [r for r in rates if r['value_inc_vat'] <= threshold]

if __name__ == "__main__":
    # Test
    client = OctopusClient("AGILE-18-02-21", "C")
    rates = client.get_rates()
    print(f"Fetched {len(rates)} rates.")
    
    if rates:
        cheapest = client.find_cheapest_blocks(rates, 3)
        print("\nCheapest 3 hours:")
        for r in cheapest:
            print(f"{r['valid_from']} - {r['valid_to']}: {r['value_inc_vat']} p/kWh")
            
        negative = client.get_negative_rates(rates)
        print(f"\nNegative rates (<= 0): {len(negative)} slots found.")
        for r in negative:
            print(f"{r['valid_from']} - {r['valid_to']}: {r['value_inc_vat']} p/kWh")
