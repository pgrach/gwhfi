import datetime

# Raw data parsed from your logs
# [2025-12-19T02:23:31] ON
# [2025-12-19T03:03:59] OFF
# [2025-12-19T04:03:12] ON
# [2025-12-19T04:21:59] OFF
# [2025-12-19T05:30:16] ON
# [2025-12-19T05:46:08] OFF

power_kw = 3.05 # Average from logs (3062W, 3058W)

events = [
    ("02:00", "02:23", "03:00", 37), # Start later in the hour
    ("03:00", "03:00", "03:04", 4),  # Tail end of previous run
    ("04:00", "04:03", "04:22", 19),
    ("05:00", "05:30", "05:46", 16)
]

print("--- Calculated Energy from Raw Data ---")
for label, start, end, mins in events:
    hours = mins / 60.0
    kwh = power_kw * hours
    print(f"Hour {label}: {mins} mins ON = {kwh:.2f} kWh")
