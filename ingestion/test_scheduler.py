import sys
import logging
from config import Config
from services.smart_scheduler import SmartScheduler
from octopus_client import OctopusClient
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)

print("Fetching rates...")
octopus = OctopusClient(Config.OCTOPUS_PRODUCT_CODE, Config.OCTOPUS_REGION_CODE)
rates = octopus.get_rates()

now = datetime.now(timezone.utc)
future_rates = [r for r in rates if r['valid_to'] > now]

print(f"Total rates fetched: {len(rates)}, Future rates: {len(future_rates)}")

if not future_rates:
    print("No future rates!")
    sys.exit(0)

today = now.date()
tomorrow = today + timedelta(days=1)

scheduler = SmartScheduler(Config)
today_slots = scheduler.compute_schedule_for_date(
    target_date=today,
    rates=rates,
    budget_hours=Config.DAILY_HEATING_BUDGET_HOURS,
    max_price=Config.ABSOLUTE_MAX_PRICE,
    use_below_average=Config.USE_BELOW_AVERAGE,
    blocked_hours=Config.BLOCKED_HOURS
)

has_tomorrow = scheduler.has_tomorrow_rates(rates, now)
tomorrow_slots = []
if has_tomorrow:
    tomorrow_slots = scheduler.compute_schedule_for_date(
        target_date=tomorrow,
        rates=rates,
        budget_hours=Config.DAILY_HEATING_BUDGET_HOURS,
        max_price=Config.ABSOLUTE_MAX_PRICE,
        use_below_average=Config.USE_BELOW_AVERAGE,
        blocked_hours=Config.BLOCKED_HOURS
    )

slots = today_slots + tomorrow_slots

print(f"Slots allocated: {len(slots)}")
for s in slots:
    print(s['valid_from'], "->", s['valid_to'], "Price:", s['value_inc_vat'])
