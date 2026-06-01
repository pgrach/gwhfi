This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Architecture & Running

This project consists of three main components:

1.  **Frontend (Next.js)**: The modern web dashboard for visualization.
2.  **Controller (Python)**: Local service that controls the heaters based on Octopus Agile rates (via Tuya).
3.  **Data Worker (Python)**: Background service that ingests real-time power data from Shelly Cloud to Supabase.

### ⚙️ System Logic (New Features)

*   **Smart Scheduling**: Daily heating slots are calculated based on the cheapest Octopus Agile rates.
*   **Afternoon Boost**: Ensures at least 1 hour of heating between 14:00-16:00 (lowest price in window) to provide hot water for the evening.
*   **Peak Heating**: The main heater runs only during negative pricing or extreme lows.
*   **Smart Cooldown**: If the heater is ON but the Shelly sensor reports <10W (tank full), the system forces a 90-minute cooldown to save energy.
*   **Grace Period**: The system ignores "0 Watt" readings for the first 30 minutes after a blocked period (16:00-19:00) to allow for mechanical timer drift.

### 🚀 How to Run (Production)

**Environment Variables**:
Ensure your `.env` (or Railway variables) includes:
*   `BLOCKED_HOURS=[7, 8, 16, 17, 18]`
*   Tuya Credentials (`TUYA_ACCESS_ID`, `TUYA_ACCESS_KEY`, etc.)
*   `STORAGE_HEATER_ENABLED=false` and `OFF_PEAK_HEATER_TARGET=main` for the normal one-heater setup where Heater 2 / Storage is physically switched off.
*   `TUYA_CONTROL_MODE=cloud` by default. Use `local` to avoid Tuya Cloud commands, or `local_then_cloud` to try LAN control first.
*   For local Tuya control, set `TUYA_LOCAL_KEY_MAIN`, `TUYA_LOCAL_KEY_SECOND`, and optionally `TUYA_DEVICE_IP_MAIN`, `TUYA_DEVICE_IP_SECOND`, `TUYA_PROTOCOL_VERSION_MAIN`, `TUYA_PROTOCOL_VERSION_SECOND`, `TUYA_LOCAL_DPS_MAIN`, `TUYA_LOCAL_DPS_SECOND`.
*   Local Tuya control only works when this Python controller runs on the same LAN as the heater switches, unless the LAN is reachable over a VPN/tunnel.
*   Optional Shelly relay control: set `MAIN_HEATER_CONTROL=shelly` and `SHELLY_RELAY_CHANNEL_MAIN=0` only if the Shelly relay is physically wired to switch the usable heater or contactor.
*   `SMART_COOLDOWN_ENABLED=false` (default). Set to `true` only if low Shelly power should turn the storage heater off for cooldown during an active slot.
*   `STRICT_TIME_CHECK=false` (default). Set to `true` only if the controller should abort when NTP is unreachable.
*   (Optional, for landing page pilot lead notifications) `RESEND_API_KEY`, `LEADS_FROM_EMAIL`, `LEADS_TO_EMAIL`
*   **Important**: If Tuya control stops working, run `python diagnose.py` and verify your **IoT Core Trial/API subscription** has not expired or exhausted quota in the Tuya Console.

**Start Script**:
Use the helper script to run both services:
```bash
./start.sh
```
*(On Windows, use `run.bat`)*

### 🛠 Diagnostics
If you suspect connectivity issues, run the included diagnostic tool:
```bash
python diagnose.py
```
This will check the status of:
1.  Tuya API Connection (Main + Second Heater)
2.  Shelly API Connection (Power Readings)

To test switching without waiting for a scheduled slot:
```bash
python ingestion/set_heater.py storage on
python ingestion/set_heater.py storage off
python ingestion/set_heater.py shelly-main on
```

See `docs/HEATER_SETUP.md` for the current physical heater setup and routing assumptions.
