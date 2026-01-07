import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL!;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_KEY!;

const supabase = createClient(supabaseUrl, supabaseKey);

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    console.log('Received Shelly webhook:', JSON.stringify(body, null, 2));

    // Validate webhook data
    if (!body || typeof body !== 'object') {
      return NextResponse.json(
        { error: 'Invalid webhook payload' },
        { status: 400 }
      );
    }

    // Extract device ID from webhook
    // Shelly webhooks typically include device info in the payload
    const deviceId = body.device?.id || body.id || process.env.SHELLY_DEVICE_ID;

    if (!deviceId) {
      return NextResponse.json(
        { error: 'Missing device ID' },
        { status: 400 }
      );
    }

    // Parse energy meter data
    // Shelly EM devices send data in different formats depending on configuration
    const rowsToInsert = [];

    // Handle Shelly EM format (emeters array)
    if (body.emeters && Array.isArray(body.emeters)) {
      for (let idx = 0; idx < body.emeters.length; idx++) {
        const emeter = body.emeters[idx];
        rowsToInsert.push({
          device_id: deviceId,
          channel: idx,
          power_w: emeter.power || 0,
          voltage: emeter.voltage || 0,
          energy_total_wh: emeter.total || 0,
          created_at: new Date().toISOString()
        });
      }
    }
    // Handle single emeter data
    else if (body.power !== undefined || body.voltage !== undefined) {
      rowsToInsert.push({
        device_id: deviceId,
        channel: body.channel || 0,
        power_w: body.power || 0,
        voltage: body.voltage || 0,
        energy_total_wh: body.total || body.energy_total_wh || 0,
        created_at: new Date().toISOString()
      });
    }
    // Handle generic webhook event format
    else if (body.event && body.event_data) {
      const eventData = body.event_data;
      rowsToInsert.push({
        device_id: deviceId,
        channel: eventData.channel || 0,
        power_w: eventData.power || 0,
        voltage: eventData.voltage || 0,
        energy_total_wh: eventData.total || 0,
        created_at: new Date().toISOString()
      });
    }
    else {
      console.warn('Unknown webhook format, storing raw data');
      // Store whatever data we received
      rowsToInsert.push({
        device_id: deviceId,
        channel: 0,
        power_w: body.power_w || body.power || 0,
        voltage: body.voltage || 0,
        energy_total_wh: body.energy_total_wh || body.total || 0,
        created_at: new Date().toISOString()
      });
    }

    if (rowsToInsert.length === 0) {
      return NextResponse.json(
        { error: 'No valid energy data found in webhook payload' },
        { status: 400 }
      );
    }

    // Insert into Supabase
    const { data, error } = await supabase
      .from('energy_readings')
      .insert(rowsToInsert);

    if (error) {
      console.error('Supabase insert error:', error);
      return NextResponse.json(
        { error: 'Database insert failed', details: error.message },
        { status: 500 }
      );
    }

    console.log(`✅ Successfully logged ${rowsToInsert.length} readings from Shelly webhook`);

    return NextResponse.json({
      success: true,
      message: `Logged ${rowsToInsert.length} readings`,
      readings: rowsToInsert
    });

  } catch (error) {
    console.error('Webhook processing error:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        details: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    );
  }
}

// Health check endpoint
export async function GET() {
  return NextResponse.json({
    status: 'ok',
    message: 'Shelly webhook endpoint is ready',
    timestamp: new Date().toISOString()
  });
}
