# Hybrid Data Collection Setup

This setup combines webhooks (instant updates) with scheduled polling (continuous monitoring) to ensure complete energy data collection.

## Components

1. **Webhooks** - Instant updates when heater state changes
2. **Scheduled Polling** - Regular data collection every 2 minutes

## Setup Instructions

### Part 1: Webhooks (Already Configured)

Your Shelly devices are already configured to send webhooks to:
```
https://gwhfi.com/api/webhook/shelly
```

These trigger when:
- Heater turns on/off
- Power crosses thresholds (over/under 10W)

### Part 2: Scheduled Polling

We'll use a free external cron service to call the polling endpoint every 2 minutes.

#### Option A: cron-job.org (Recommended - Free)

1. **Sign up**
   - Go to: https://cron-job.org
   - Create a free account (no credit card required)

2. **Create a new cron job**
   - Click "Create cronjob"
   - **Title**: `Shelly Data Polling`
   - **URL**: `https://gwhfi.com/api/cron/shelly-poll`
   - **Schedule**: Every `2` minutes
   - **Enable**: ✓

3. **Save and activate**
   - Click "Create cronjob"
   - The job will start running immediately

#### Option B: EasyCron (Alternative - Free)

1. **Sign up**
   - Go to: https://www.easycron.com
   - Create free account

2. **Add cron job**
   - URL: `https://gwhfi.com/api/cron/shelly-poll`
   - Cron Expression: `*/2 * * * *`
   - Enable

#### Option C: GitHub Actions (For Git Users)

Create `.github/workflows/poll-shelly.yml`:

```yaml
name: Poll Shelly Data

on:
  schedule:
    - cron: '*/2 * * * *'  # Every 2 minutes
  workflow_dispatch:  # Manual trigger

jobs:
  poll:
    runs-on: ubuntu-latest
    steps:
      - name: Call polling endpoint
        run: curl https://gwhfi.com/api/cron/shelly-poll
```

## Testing

### Test the polling endpoint manually:

```bash
curl https://gwhfi.com/api/cron/shelly-poll
```

Expected response:
```json
{
  "success": true,
  "message": "Logged 2 readings",
  "readings": [
    {
      "device_id": "48e72969030f",
      "channel": 0,
      "power_w": 0,
      "voltage": 245.1,
      "energy_total_wh": 1072.5,
      "created_at": "2026-01-07T12:30:00.000Z"
    },
    {
      "device_id": "48e72969030f",
      "channel": 1,
      "power_w": 2956,
      "voltage": 245.1,
      "energy_total_wh": 73300,
      "created_at": "2026-01-07T12:30:00.000Z"
    }
  ]
}
```

### Monitor Railway logs:

Go to Railway → vibrant-emotion → Deploy Logs

You should see:
```
🔄 Polling Shelly device for data...
📊 Channel 0: 0W | 245.1V | 1072.5Wh
📊 Channel 1: 2956W | 245.1V | 73300Wh
✅ Logged 2 readings to Supabase
```

## How It Works Together

### Webhooks (Instant - Event-driven)
- Heater turns ON → Webhook fires → Data saved immediately
- Heater turns OFF → Webhook fires → Data saved immediately
- Power spikes/drops → Webhook fires → Data saved immediately

### Polling (Every 2 minutes - Continuous)
- Ensures no gaps in data even if webhooks fail
- Captures gradual power changes
- Provides reliable baseline monitoring
- Uses cumulative energy (total_wh) to ensure accuracy

### Result
- **Complete energy data** - no missed consumption
- **Real-time updates** for state changes
- **Reliable monitoring** even if webhooks are delayed
- **Maximum 2-minute gap** between data points

## Troubleshooting

### No data appearing in dashboard

1. **Test the polling endpoint**:
   ```bash
   curl https://gwhfi.com/api/cron/shelly-poll
   ```

2. **Check Railway logs** for errors

3. **Verify cron job is running** in your cron service dashboard

### Duplicate data

If you see the same reading twice:
- This is normal! Webhooks and polling may save the same state
- Your dashboard aggregates data, so duplicates won't affect charts

### Rate limit errors

If you see 429 errors:
- Increase polling interval to 3 or 5 minutes
- Webhooks will still provide instant updates

## Estimated API Usage

With hybrid approach:
- **Polling**: ~720 requests/day (every 2 minutes)
- **Webhooks**: ~10-50 requests/day (depends on heater activity)
- **Total**: ~800 requests/day

This is well below any reasonable rate limit and ensures complete data coverage.
