# Shelly Webhook Setup Guide

This guide explains how to configure your Shelly device to send real-time data updates via webhooks instead of polling.

## Benefits of Webhook Approach

- ✅ **Instant updates** - Data appears immediately when power consumption changes
- ✅ **Lower latency** - No 60-second polling delay
- ✅ **Reduced API calls** - Only sends data when events occur
- ✅ **More efficient** - No need for separate cloud_worker process

## Step 1: Get Your Webhook URL

Your webhook endpoint is:
```
https://your-railway-app.railway.app/api/webhook/shelly
```

Replace `your-railway-app` with your actual Railway deployment URL.

You can test if the endpoint is working by visiting:
```
https://your-railway-app.railway.app/api/webhook/shelly
```
It should return: `{"status":"ok","message":"Shelly webhook endpoint is ready",...}`

## Step 2: Configure Shelly Device Webhook

### Option A: Via Shelly Web Interface (Recommended)

1. **Access your Shelly device's web interface**
   - Find your device's local IP address (check your router or Shelly app)
   - Open browser and go to: `http://[DEVICE_IP]`

2. **Navigate to Settings > Actions (or Webhooks)**
   - Different Shelly generations have different UI layouts
   - Look for "Actions", "Webhooks", or "Internet & Security" section

3. **Add a new webhook action**
   - **Trigger/Event**: Set to trigger on power change or periodic report
   - **URL**: Enter your webhook URL: `https://your-railway-app.railway.app/api/webhook/shelly`
   - **Method**: POST
   - **Condition**: (Optional) Set minimum interval to avoid too many requests (e.g., every 5-10 seconds)

4. **Configure the payload** (if customizable)
   - Make sure it includes: `power`, `voltage`, `total` (energy)
   - Example payload format:
   ```json
   {
     "id": "shellyem-XXXXXX",
     "emeters": [
       {
         "power": 1234.5,
         "voltage": 230.1,
         "total": 12345
       }
     ]
   }
   ```

5. **Save and test**
   - Save the webhook configuration
   - Test by toggling a device or waiting for power change
   - Check Railway logs to see if webhook was received

### Option B: Via Shelly Cloud API

If you prefer to configure via API:

```bash
curl -X POST "https://shelly-YOURREGION-api.shelly.cloud/device/action" \
  -d "auth_key=YOUR_SHELLY_AUTH_KEY" \
  -d "id=YOUR_DEVICE_ID" \
  -d "actions=[{
    'name': 'webhook_to_railway',
    'urls': ['https://your-railway-app.railway.app/api/webhook/shelly'],
    'condition': 'emeter.power > 0',
    'enabled': true
  }]"
```

### Option C: Via Shelly Scripts (Gen2+ devices)

For Shelly Gen2 devices, you can use scripts:

```javascript
// Script to send periodic updates every 10 seconds
let CONFIG = {
  webhookUrl: "https://your-railway-app.railway.app/api/webhook/shelly",
  interval: 10000 // 10 seconds
};

function sendData() {
  let status = Shelly.getComponentStatus("em:0");

  let payload = {
    device: { id: Shelly.getDeviceInfo().id },
    emeters: [{
      power: status.apower,
      voltage: status.voltage,
      total: status.total_act_energy
    }]
  };

  Shelly.call("HTTP.POST", {
    url: CONFIG.webhookUrl,
    content_type: "application/json",
    body: JSON.stringify(payload)
  });
}

// Send data every interval
Timer.set(CONFIG.interval, true, sendData);
```

## Step 3: Environment Variables

Make sure these are set in your Railway deployment:

```env
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key  # Preferred for webhooks
SHELLY_DEVICE_ID=your_shelly_device_id
```

## Step 4: Update Railway Deployment

### Remove the old cloud_worker:

1. **Update Procfile** - Remove or comment out the worker line:
   ```
   web: npm run start
   # worker: python ingestion/cloud_worker.py  # No longer needed with webhooks
   ```

2. **Redeploy to Railway**
   - Commit and push changes
   - Railway will automatically redeploy with only the web service

3. **Stop the old worker service** (if it's a separate deployment)
   - Go to Railway dashboard
   - Find the `cloud_worker` service
   - Delete or pause it

## Step 5: Verify It's Working

1. **Check Railway logs**
   ```bash
   # In Railway dashboard, view logs for your web service
   # You should see: "Received Shelly webhook: ..." when data arrives
   ```

2. **Monitor your dashboard**
   - Open your Smart Water dashboard
   - Power consumption should update instantly when it changes

3. **Test the webhook manually** (optional)
   ```bash
   curl -X POST https://your-railway-app.railway.app/api/webhook/shelly \
     -H "Content-Type: application/json" \
     -d '{
       "id": "test-device",
       "emeters": [{
         "power": 1500,
         "voltage": 230,
         "total": 10000
       }]
     }'
   ```

## Troubleshooting

### Webhook not receiving data
- Check Shelly device can reach your Railway URL (not blocked by firewall)
- Verify the webhook URL is correct in Shelly settings
- Check Railway logs for error messages

### Data format errors
- The webhook endpoint handles multiple Shelly formats automatically
- Check Railway logs to see the exact payload being received
- You may need to adjust the webhook configuration on your Shelly device

### Authentication issues
- Make sure `SUPABASE_SERVICE_ROLE_KEY` is set (preferred over anon key for server-side operations)
- Check Supabase Row Level Security (RLS) policies allow inserts

## Advanced Configuration

### Rate Limiting
To avoid overwhelming your database with too many updates:

1. **On Shelly device**: Set minimum interval between webhook calls (e.g., 5-10 seconds)
2. **Add throttling to webhook endpoint**: Implement debouncing logic if needed

### Security
Consider adding webhook authentication:
- Add a secret token to your webhook URL query string
- Validate the token in the API route before processing

Example:
```typescript
// In route.ts
const webhookSecret = process.env.WEBHOOK_SECRET;
const providedSecret = request.nextUrl.searchParams.get('secret');

if (providedSecret !== webhookSecret) {
  return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
}
```

Then use URL: `https://your-app.railway.app/api/webhook/shelly?secret=YOUR_SECRET`

## What Happens to cloud_worker.py?

You can:
- **Keep it as backup**: Comment it out in Procfile but keep the file
- **Delete it entirely**: Remove the file and its dependencies from requirements.txt
- **Use for fallback**: Run it occasionally to backfill any missed data

The webhook approach is more efficient and real-time, so the worker is no longer necessary for normal operation.
