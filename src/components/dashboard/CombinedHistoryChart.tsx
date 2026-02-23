"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceArea,
    ReferenceLine
} from "recharts"
import { getUKDateBoundaries, getUKDateBoundariesForDate } from "@/lib/date-utils"

interface Rate {
    value_inc_vat: number
    valid_from: string
    valid_to: string
}

interface ScheduleSlot {
    slot_start: string
    slot_end: string
    price: number
    heater_type: string
}

export function CombinedHistoryChart() {
    const [data, setData] = useState<any[]>([])
    const [viewMode, setViewMode] = useState<"today" | "tomorrow" | "7d" | "30d" | "custom">("today")
    const [customDate, setCustomDate] = useState<string>(() => {
        // Default to yesterday in local time
        const d = new Date()
        d.setDate(d.getDate() - 1)
        return d.toISOString().split('T')[0]
    })
    const [hasRates, setHasRates] = useState(true)
    const [totals, setTotals] = useState({ peak: 0, offPeak: 0 })
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
    const [channelVisible, setChannelVisible] = useState({ peak: true, offPeak: true })

    // Configuration for Octopus
    const PRODUCT = "AGILE-24-10-01"
    const REGION = "C" // London
    const TARIFF = `E-1R-${PRODUCT}-${REGION}`

    useEffect(() => {
        const fetchData = async () => {

            // 1. Define Timeline Boundaries (always in UK time)
            let startDate: Date
            let endDate: Date

            if (viewMode === "today") {
                const { start, end } = getUKDateBoundaries(0)
                startDate = start
                endDate = end
            } else if (viewMode === "tomorrow") {
                const { start, end } = getUKDateBoundaries(1)
                startDate = start
                endDate = end
            } else if (viewMode === "7d") {
                const { start } = getUKDateBoundaries(-7)
                const { end } = getUKDateBoundaries(0)
                startDate = start
                endDate = end
            } else if (viewMode === "custom") {
                const { start, end } = getUKDateBoundariesForDate(customDate)
                startDate = start
                endDate = end
            } else {
                // 30d
                const { start } = getUKDateBoundaries(-30)
                const { end } = getUKDateBoundaries(0)
                startDate = start
                endDate = end
            }

            const startIso = startDate.toISOString()
            const endIso = endDate.toISOString()

            // 2. Fetch Data
            let rates: Rate[] = []
            let readings: any[] = []
            let scheduleSlots: ScheduleSlot[] = []
            let channelHasEnergyMovement = new Map<number, boolean>([
                [0, true],
                [1, true],
            ])

            // Explicitly ensure we fetch enough future data if viewing tomorrow
            const ratesPromise = fetch(
                `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?period_from=${startIso}&page_size=1500`
            ).then(r => r.json())

            // Define bucket size based on view mode
            // Today/Tomorrow = 1 min (Raw data)
            // 7d = 1 hour (Aggregated)
            // 30d = 1 hour (Aggregated) or maybe 4 hours? Let's try 1h first.
            // ALWAYS use RPC downsampling to avoid Supabase's 1000-row limit
            const bucketMinutes = (viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom") ? 1 : 60

            const readingsPromise = supabase
                .rpc('get_downsampled_readings', {
                    start_time: startIso,
                    end_time: endIso,
                    bucket_seconds: bucketMinutes * 60
                })

            // Fetch scheduled heating slots from Supabase
            const schedulePromise = supabase
                .from('heating_schedule')
                .select('*')
                .gte('slot_start', startIso)
                .lte('slot_end', endIso)
                .order('slot_start', { ascending: true })

            const channelMovementPromise = Promise.all([0, 1].map(async (channel) => {
                const [firstRes, lastRes] = await Promise.all([
                    supabase
                        .from('energy_readings')
                        .select('energy_total_wh, created_at')
                        .eq('channel', channel)
                        .gte('created_at', startIso)
                        .lte('created_at', endIso)
                        .order('created_at', { ascending: true })
                        .limit(1),
                    supabase
                        .from('energy_readings')
                        .select('energy_total_wh, created_at')
                        .eq('channel', channel)
                        .gte('created_at', startIso)
                        .lte('created_at', endIso)
                        .order('created_at', { ascending: false })
                        .limit(1),
                ])

                if (firstRes.error || lastRes.error || !firstRes.data?.[0] || !lastRes.data?.[0]) {
                    return { channel, hasMovement: true }
                }

                const firstWh = Number(firstRes.data[0].energy_total_wh ?? 0)
                const lastWh = Number(lastRes.data[0].energy_total_wh ?? 0)
                return { channel, hasMovement: Math.abs(lastWh - firstWh) > 0.1 }
            }))

            try {
                const [rData, sData, schedData, movementData] = await Promise.all([ratesPromise, readingsPromise, schedulePromise, channelMovementPromise])
                if (rData.results) {
                    rates = rData.results
                    if (rates.length === 0 && viewMode === "tomorrow") {
                        setHasRates(false)
                    } else {
                        setHasRates(true)
                    }
                }

                if (sData.data) {
                    readings = sData.data
                } else if (sData.error) {
                    console.error("Supabase Error:", sData.error)
                }

                if (schedData.data) {
                    scheduleSlots = schedData.data
                } else if (schedData.error) {
                    console.error("Schedule fetch error:", schedData.error)
                }

                channelHasEnergyMovement = new Map<number, boolean>(movementData.map((m) => [m.channel, m.hasMovement]))
                setChannelVisible({
                    peak: !!channelHasEnergyMovement.get(0),
                    offPeak: !!channelHasEnergyMovement.get(1),
                })
            } catch (e) {
                console.error("Fetch error", e)
                setHasRates(false)
            }

            // Track last update time from most recent reading
            if (readings.length > 0) {
                const latestReading = readings.reduce((latest, current) => {
                    const currentTime = new Date(current.bucket_time)
                    const latestTime = new Date(latest.bucket_time)
                    return currentTime > latestTime ? current : latest
                })
                setLastUpdate(new Date(latestReading.bucket_time))
            }

            // --- Calculate Totals (kWh) ---
            // For long view, we can sum the avg_power * hours? 
            // Or just keep the total calculation roughly same?
            // Actually, for accurate totals, we might want a separate RPC or just accept approximation.
            // But the user cares about the graph mainly.
            // Let's mock totals for now if RPC, or calculate from averages (avg power W * hours = Wh).

            const calculateKWh = (channelId: number) => {
                // Always using RPC now, calculate from avg_power
                const channelReadings = readings.filter(r => r.channel === channelId)
                const hours = bucketMinutes / 60
                const totalWh = channelReadings.reduce((sum, r) => sum + ((r.avg_power || 0) * hours), 0)
                return totalWh / 1000
            }

            setTotals({
                peak: calculateKWh(0),
                offPeak: calculateKWh(1)
            })
            // -----------------------------

            // --- Build Schedule Map for "Scheduled Heating" visualization ---
            // Create a Set of timestamps where heating is scheduled
            // This replaces the old "below average" logic with actual scheduled slots
            const scheduledMap = new Map<number, boolean>()

            scheduleSlots.forEach(slot => {
                const slotStart = new Date(slot.slot_start).getTime()
                const slotEnd = new Date(slot.slot_end).getTime()

                // Mark every 30-min boundary within this slot as scheduled
                let t = slotStart
                while (t < slotEnd) {
                    scheduledMap.set(t, true)
                    t += 30 * 60 * 1000 // 30 minutes in ms
                }
            })
            // -------------------------------------------------


            // 3. Build Unified Buckets (Dynamic Granularity)

            const buckets = []
            const currentCursor = new Date(startDate)

            // Map for quick lookup
            const readingsBySlot = new Map<number, any[]>()
            readings.forEach(r => {
                // Always using RPC now, so always use bucket_time
                const t = new Date(r.bucket_time)

                // Align to bucket using UTC methods to avoid local timezone offset
                const remainder = t.getUTCMinutes() % bucketMinutes
                t.setUTCMinutes(t.getUTCMinutes() - remainder, 0, 0)

                const key = t.getTime()
                if (!readingsBySlot.has(key)) readingsBySlot.set(key, [])
                readingsBySlot.get(key)?.push(r)
            })

            rates.sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())

            const isDayView = viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom"
            while (currentCursor <= endDate) {
                const timestamp = currentCursor.toLocaleString([], {
                    timeZone: 'Europe/London',
                    month: isDayView ? undefined : 'numeric',
                    day: isDayView ? undefined : 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                })
                const slotTime = currentCursor.getTime()

                // Find Rate
                const rateObj = rates.find(r => {
                    const from = new Date(r.valid_from).getTime()
                    const to = new Date(r.valid_to).getTime()
                    return slotTime >= from && slotTime < to
                })

                // Determine if this slot is scheduled for heating
                // Align to 30-min boundary to match schedule slots
                const alignedTime = Math.floor(slotTime / (30 * 60 * 1000)) * (30 * 60 * 1000)
                const isScheduled = scheduledMap.has(alignedTime)

                const slotReadings = readingsBySlot.get(slotTime) || []

                // No reading in this bucket = heater is off (0W)
                const defaultPower = 0
                let avg0 = defaultPower
                let avg1 = defaultPower

                // Always using RPC now, so always use avg_power
                const r0 = slotReadings.find(r => r.channel === 0)
                const r1 = slotReadings.find(r => r.channel === 1)
                avg0 = r0 ? r0.avg_power : defaultPower
                avg1 = r1 ? r1.avg_power : defaultPower

                if (!channelHasEnergyMovement.get(0)) {
                    avg0 = 0
                }
                if (!channelHasEnergyMovement.get(1)) {
                    avg1 = 0
                }

                buckets.push({
                    timestamp,
                    raw_time: slotTime,
                    rate: rateObj ? rateObj.value_inc_vat : null,
                    isScheduled: isScheduled,
                    power_0: avg0,
                    power_1: avg1
                })

                currentCursor.setUTCMinutes(currentCursor.getUTCMinutes() + bucketMinutes)
            }

            setData(buckets)
        }

        fetchData()
    }, [viewMode, customDate])

    // Identify "off" periods for shading (both heaters at 0W or null)
    const offPeriods: Array<{ start: string; end: string }> = []
    let offStart: string | null = null

    data.forEach((point, idx) => {
        const isBothOff = (point.power_0 === null || point.power_0 === 0) &&
            (point.power_1 === null || point.power_1 === 0)

        if (isBothOff && offStart === null) {
            // Start of off period
            offStart = point.timestamp
        } else if (!isBothOff && offStart !== null) {
            // End of off period
            offPeriods.push({ start: offStart, end: data[idx - 1]?.timestamp || offStart })
            offStart = null
        }
    })

    // Close any open off period at the end
    if (offStart !== null && data.length > 0) {
        offPeriods.push({ start: offStart, end: data[data.length - 1].timestamp })
    }

    // Custom Dot for Scheduled Heating Slots (Only show every 30 mins to avoid clutter)
    const ScheduledDot = (props: any) => {
        const { cx, cy, payload } = props;
        if (payload && payload.isScheduled) {
            // Check if on 30-min boundary (use UTC to avoid timezone issues)
            const date = new Date(payload.raw_time)
            const min = date.getUTCMinutes()
            if (min % 30 === 0) {
                return (
                    <circle cx={cx} cy={cy} r={4} fill="#10b981" stroke="#fff" strokeWidth={1} />
                );
            }
        }
        return null;
    };

    // Check for missing Tomorrow data
    // We check hasRates because 'data' might be populated with empty buckets
    if (viewMode === "tomorrow" && !hasRates) {
        return (
            <Card className="col-span-4">
                <CardHeader>
                    <CardTitle>Usage & Price History</CardTitle>
                </CardHeader>
                <CardContent className="h-[400px] flex items-center justify-center">
                    <div className="text-center space-y-4">
                        <Button variant="outline" size="sm" onClick={() => setViewMode("today")}>
                            Back to Today
                        </Button>
                        <p className="text-muted-foreground">
                            Tomorrow's rates are not yet available from Octopus Energy. <br />
                            Please check back after 4:00 PM.
                        </p>
                    </div>
                </CardContent>
            </Card>
        )
    }

    // Helper to format time ago
    const formatTimeAgo = (date: Date | null) => {
        if (!date) return "Never"
        const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000)
        if (seconds < 60) return `${seconds}s ago`
        const minutes = Math.floor(seconds / 60)
        if (minutes < 60) return `${minutes}m ago`
        const hours = Math.floor(minutes / 60)
        if (hours < 24) return `${hours}h ago`
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    const systemStatus = lastUpdate && (new Date().getTime() - lastUpdate.getTime()) < 120000 ? "active" : "stale"

    // Find current time position for vertical highlight
    const now = new Date()
    let currentTimestamp = null

    if (data.length > 0) {
        // Find the closest data point to current time
        const nowTime = now.getTime()
        let closestPoint = data[0]
        let minDiff = Math.abs(data[0].raw_time - nowTime)

        for (const point of data) {
            const diff = Math.abs(point.raw_time - nowTime)
            if (diff < minDiff) {
                minDiff = diff
                closestPoint = point
            }
            // If we've passed "now", break early
            if (point.raw_time > nowTime) break
        }

        // Only show if the closest point is reasonably close to now
        // (within the view period)
        const maxDiff = (viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom") ? 60000 : 3600000
        if (minDiff < maxDiff) {
            currentTimestamp = closestPoint
        }
    }

    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-col space-y-4 sm:flex-row sm:items-center sm:justify-between sm:space-y-0 pb-2">
                <div className="space-y-1">
                    <div className="flex items-center gap-3">
                        <CardTitle className="text-xl sm:text-2xl">Usage & Price History</CardTitle>
                        {lastUpdate && (
                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${systemStatus === "active"
                                ? "bg-green-500/10 text-green-600 border border-green-500/20"
                                : "bg-orange-500/10 text-orange-600 border border-orange-500/20"
                                }`}>
                                <div className={`w-1.5 h-1.5 rounded-full ${systemStatus === "active" ? "bg-green-500" : "bg-orange-500"
                                    } animate-pulse`} />
                                <span>Updated {formatTimeAgo(lastUpdate)}</span>
                            </div>
                        )}
                    </div>
                    <CardDescription className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0">
                        <span>Total heater usage in selected range:</span>
                        <span className="hidden sm:inline text-muted-foreground mx-2">|</span>
                        <div className="flex gap-4 sm:gap-0">
                            <span className="text-blue-500 font-bold whitespace-nowrap">Boost: {totals.peak.toFixed(2)} kWh</span>
                            <span className="hidden sm:inline text-muted-foreground mx-2">|</span>
                            <span className="text-green-600 font-bold whitespace-nowrap">Storage: {totals.offPeak.toFixed(2)} kWh</span>
                        </div>
                    </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2 items-center">
                    <Button variant={viewMode === "today" ? "default" : "outline"} size="sm" onClick={() => setViewMode("today")}>Today</Button>
                    <Button variant={viewMode === "tomorrow" ? "default" : "outline"} size="sm" onClick={() => setViewMode("tomorrow")}>Tomorrow</Button>
                    <Button variant={viewMode === "7d" ? "default" : "outline"} size="sm" onClick={() => setViewMode("7d")}>7d</Button>
                    <Button variant={viewMode === "30d" ? "default" : "outline"} size="sm" onClick={() => setViewMode("30d")}>30d</Button>
                    <input
                        type="date"
                        max={new Date(new Date().setDate(new Date().getDate() - 1)).toISOString().split('T')[0]}
                        value={customDate}
                        onChange={(e) => {
                            if (e.target.value) {
                                setCustomDate(e.target.value)
                                setViewMode("custom")
                            }
                        }}
                        className={`h-9 rounded-md border px-2 text-sm cursor-pointer
                            ${viewMode === "custom"
                                ? "bg-primary text-primary-foreground border-primary"
                                : "bg-background border-input text-foreground hover:bg-accent hover:text-accent-foreground"
                            }`
                        }
                    />
                </div>
            </CardHeader>
            <CardContent className="pl-2">
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />

                            {/* Shade off periods */}
                            {offPeriods.map((period, idx) => (
                                <ReferenceArea
                                    key={`off-${idx}`}
                                    x1={period.start}
                                    x2={period.end}
                                    yAxisId="right"
                                    fill="#64748b"
                                    fillOpacity={0.08}
                                    strokeOpacity={0}
                                />
                            ))}

                            {/* Current time indicator - only show for today and 7d/30d views */}
                            {currentTimestamp && viewMode === "today" && (
                                <ReferenceLine
                                    x={currentTimestamp.timestamp}
                                    yAxisId="left"
                                    stroke="#3b82f6"
                                    strokeWidth={2}
                                    strokeDasharray="4 2"
                                    label={{
                                        value: "NOW",
                                        position: "top",
                                        fill: "#3b82f6",
                                        fontSize: 11,
                                        fontWeight: 700
                                    }}
                                />
                            )}

                            <XAxis
                                dataKey="timestamp"
                                stroke="#888888"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                minTickGap={(viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom") ? 30 : 60}
                            />
                            {/* Left Axis: Price */}
                            <YAxis
                                yAxisId="left"
                                stroke="#f050f8"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                domain={[0, 'dataMax + 5']}
                                tickFormatter={(value) => `${value}p`}
                                label={{ value: 'Agile Rate (p/kWh)', angle: -90, position: 'insideLeft', fill: '#f050f8' }}
                            />
                            {/* Right Axis: Power */}
                            <YAxis
                                yAxisId="right"
                                orientation="right"
                                stroke="#82ca9d"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}W`}
                                label={{ value: 'Power (W)', angle: 90, position: 'insideRight', fill: '#82ca9d' }}
                            />

                            <Tooltip
                                contentStyle={{ backgroundColor: "#1f2937", border: "none", color: "#fff" }}
                                formatter={(value: any, name: any, props: any) => {
                                    if (name === "Rate (p/kWh)") {
                                        const isScheduled = props.payload.isScheduled
                                        return [
                                            <div key="rate">
                                                <span>{Number(value).toFixed(2)}p</span>
                                                {isScheduled && <span className="ml-2 text-green-400 font-bold">● Heating</span>}
                                            </div>,
                                            name
                                        ]
                                    }
                                    return [`${Number(value).toFixed(0)}W`, name]
                                }}
                            />
                            <Legend />

                            {/* Rate Line (Left Axis) */}
                            <Line
                                yAxisId="left"
                                type="stepAfter"
                                dataKey="rate"
                                name="Rate (p/kWh)"
                                stroke="#f050f8"
                                strokeWidth={2}
                                dot={<ScheduledDot />}
                                connectNulls
                            />

                            {/* Heater Lines (Right Axis) */}
                            <Line
                                yAxisId="right"
                                type="stepAfter"
                                dataKey="power_0"
                                name="Boost Heater (W)"
                                stroke="#2563eb"
                                strokeWidth={2}
                                dot={false}
                                hide={!channelVisible.peak}
                            />
                            <Line
                                yAxisId="right"
                                type="stepAfter"
                                dataKey="power_1"
                                name="Storage Heater (W)"
                                stroke="#16a34a"
                                strokeWidth={2}
                                dot={false}
                                hide={!channelVisible.offPeak}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    )
}

