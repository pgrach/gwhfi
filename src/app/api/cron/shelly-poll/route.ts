import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL!;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_KEY!;
const SHELLY_AUTH_KEY = process.env.SHELLY_CLOUD_AUTH_KEY;
const SHELLY_SERVER = process.env.SHELLY_CLOUD_SERVER;
const SHELLY_DEVICE_ID = process.env.SHELLY_DEVICE_ID;

const supabase = createClient(supabaseUrl, supabaseKey);

async function getShellyStatus(deviceId: string) {
  const url = `${SHELLY_SERVER}/device/status`;
  const payload = new URLSearchParams({
    id: deviceId,
    auth_key: SHELLY_AUTH_KEY!
  });

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: payload.toString()
    });

    const data = await response.json();

    if (data.isok) {
      return data.data.device_status;
    } else {
      console.error('Shelly API Error:', data);
      return null;
    }
  } catch (error) {
    console.error('Failed to fetch Shelly status:', error);
    return null;
  }
}

export async function GET(request: NextRequest) {
  console.log('🔄 Polling Shelly device for data...');

  if (!SHELLY_DEVICE_ID || !SHELLY_AUTH_KEY || !SHELLY_SERVER) {
    console.error('Missing env vars:', {
      hasDeviceId: !!SHELLY_DEVICE_ID,
      hasAuthKey: !!SHELLY_AUTH_KEY,
      hasServer: !!SHELLY_SERVER
    });
    return NextResponse.json(
      { error: 'Missing Shelly configuration' },
      { status: 500 }
    );
  }

  const status = await getShellyStatus(SHELLY_DEVICE_ID);

  if (!status) {
    return NextResponse.json(
      { error: 'Failed to fetch Shelly data' },
      { status: 500 }
    );
  }

  const emeters = status.emeters || [];
  const rowsToInsert = [];

  for (let idx = 0; idx < emeters.length; idx++) {
    const emeter = emeters[idx];
    const row = {
      device_id: SHELLY_DEVICE_ID,
      channel: idx,
      power_w: emeter.power || 0,
      voltage: emeter.voltage || 0,
      energy_total_wh: emeter.total || 0,
      created_at: new Date().toISOString()
    };
    rowsToInsert.push(row);
    console.log(`📊 Channel ${idx}: ${emeter.power}W | ${emeter.voltage}V | ${emeter.total}Wh`);
  }

  if (rowsToInsert.length > 0) {
    const { data, error } = await supabase
      .from('energy_readings')
      .insert(rowsToInsert);

    if (error) {
      console.error('❌ Supabase insert error:', error);
      return NextResponse.json(
        { error: 'Database insert failed', details: error.message },
        { status: 500 }
      );
    }

    console.log(`✅ Logged ${rowsToInsert.length} readings to Supabase`);
  }

  return NextResponse.json({
    success: true,
    message: `Logged ${rowsToInsert.length} readings`,
    readings: rowsToInsert
  });
}
