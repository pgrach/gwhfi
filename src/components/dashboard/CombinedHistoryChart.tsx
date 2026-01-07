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
    ReferenceArea
} from "recharts"

interface Rate {
    value_inc_vat: number
    valid_from: string
    valid_to: string
}

export function CombinedHistoryChart() {
    const [data, setData] = useState<any[]>([])
    // 0 = Today (Midnight to Midnight)
    // 1 = Last 24h? No, let's stick to "Days History".
    // Let's redefine: 1 = Today+Yesterday?
    // User wants "24h". Let's assume "Today" view (00:00 - 23:59).
    const [viewMode, setViewMode] = useState<"today" | "tomorrow" | "7d" | "30d">("today")
    const [hasRates, setHasRates] = useState(true)
    const [totals, setTotals] = useState({ peak: 0, offPeak: 0 })
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

    // Configuration for Octopus
    const PRODUCT = "AGILE-18-02-21"
    const REGION = "C" // London
    const TARIFF = `E-1R-${PRODUCT}-${REGION}`

    useEffect(() => {
        const fetchData = async () => {

            // 1. Define Timeline Boundaries
            const now = new Date()
            let startDate = new Date()
            let endDate = new Date()

            if (viewMode === "today") {
                // Today 00:00 to Today 23:59
                startDate.setHours(0, 0, 0, 0)
                endDate.setHours(23, 59, 59, 999)
            } else if (viewMode === "tomorrow") {
                // Today 00:00 to Tomorrow 23:59
                // Or just Tomorrow? User usually wants to see the future plan.
                // Let's show Tomorrow 00:00 to 23:59
                startDate.setDate(startDate.getDate() + 1)
                startDate.setHours(0, 0, 0, 0)

                endDate.setDate(endDate.getDate() + 1)
                endDate.setHours(23, 59, 59, 999)
            } else if (viewMode === "7d") {
                // Last 7 days to Today 23:59
                startDate.setDate(startDate.getDate() - 7)
                startDate.setHours(0, 0, 0, 0)
                endDate.setHours(23, 59, 59, 999)
            } else if (viewMode === "30d") {
                // Last 30 days
                startDate.setDate(startDate.getDate() - 30)
                startDate.setHours(0, 0, 0, 0)
                endDate.setHours(23, 59, 59, 999)
            }

            const startIso = startDate.toISOString()
            const endIso = endDate.toISOString()

            // 2. Fetch Data
            let rates: Rate[] = []
            let readings: any[] = []

            // Explicitly ensure we fetch enough future data if viewing tomorrow
            const ratesPromise = fetch(
                `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?period_from=${startIso}&page_size=1500`
            ).then(r => r.json())

            // Define bucket size based on view mode
            // Today/Tomorrow = 1 min (Raw data)
            // 7d = 1 hour (Aggregated)
            // 30d = 1 hour (Aggregated) or maybe 4 hours? Let's try 1h first.
            // ALWAYS use RPC downsampling to avoid Supabase's 1000-row limit
            const bucketMinutes = (viewMode === "today" || viewMode === "tomorrow") ? 5 : 60
            const isLongView = viewMode === "7d" || viewMode === "30d" // Keep for compatibility with data processing

            const readingsPromise = supabase
                .rpc('get_downsampled_readings', {
                    start_time: startIso,
                    end_time: endIso,
                    bucket_seconds: bucketMinutes * 60
                })

            try {
                const [rData, sData] = await Promise.all([ratesPromise, readingsPromise])
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

            // --- Pre-process Rates for "Smart Daily" Logic ---
            // 1. Group rates by UTC Day
            const ratesByDay = new Map<string, Rate[]>()
            rates.forEach(r => {
                // Ensure we use the date part of valid_from
                const day = r.valid_from.split('T')[0]
                if (!ratesByDay.has(day)) ratesByDay.set(day, [])
                ratesByDay.get(day)?.push(r)
            })

            // 2. Calculate thresholds and tag "Smart" slots
            // We'll create a Map of "Timestamp -> isSmart" for O(1) lookup
            const smartMap = new Map<number, boolean>()

            ratesByDay.forEach((dayRates, dayKey) => {
                if (dayRates.length === 0) return

                // Calculate average for THIS day
                const sum = dayRates.reduce((a, b) => a + b.value_inc_vat, 0)
                const avg = sum / dayRates.length

                // Tag slots
                dayRates.forEach(r => {
                    const isSmart = r.value_inc_vat <= avg
                    const t = new Date(r.valid_from).getTime()
                    smartMap.set(t, isSmart)
                })
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

                // Align to bucket
                const remainder = t.getMinutes() % bucketMinutes
                t.setMinutes(t.getMinutes() - remainder, 0, 0)

                const key = t.getTime()
                if (!readingsBySlot.has(key)) readingsBySlot.set(key, [])
                readingsBySlot.get(key)?.push(r)
            })

            rates.sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())

            while (currentCursor <= endDate) {
                const timestamp = currentCursor.toLocaleString([], {
                    month: (viewMode === "today" || viewMode === "tomorrow") ? undefined : 'numeric',
                    day: (viewMode === "today" || viewMode === "tomorrow") ? undefined : 'numeric',
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

                // Determine if Smart Slot
                let isSmart = false
                if (rateObj) {
                    const rateTime = new Date(rateObj.valid_from).getTime()
                    isSmart = smartMap.get(rateTime) || false
                }

                const slotReadings = readingsBySlot.get(slotTime) || []

                // Extract power values based on mode
                // RPC: avg_power
                // Raw: power_w
                // NOTE: With sparse data (0W readings skipped), we use null for missing data
                // The chart's connectNulls will handle visualization
                let avg0 = null
                let avg1 = null

                // Always using RPC now, so always use avg_power
                const r0 = slotReadings.find(r => r.channel === 0)
                const r1 = slotReadings.find(r => r.channel === 1)
                avg0 = r0 ? r0.avg_power : null
                avg1 = r1 ? r1.avg_power : null

                buckets.push({
                    timestamp,
                    raw_time: slotTime,
                    rate: rateObj ? rateObj.value_inc_vat : null,
                    isSmart: isSmart,
                    power_0: avg0,
                    power_1: avg1
                })

                currentCursor.setMinutes(currentCursor.getMinutes() + bucketMinutes)
            }

            setData(buckets)
        }

        fetchData()
    }, [viewMode])

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

    // Custom Dot for Smart Slots (Only show every 30 mins to avoid clutter)
    const SmartDot = (props: any) => {
        const { cx, cy, payload } = props;
        if (payload && payload.isSmart) {
            // Check if on 30-min boundary
            const date = new Date(payload.raw_time)
            const min = date.getMinutes()
            if (min % 30 === 0) {
                return (
                    <circle cx={cx} cy={cy} r={3} fill="#10b981" stroke="none" />
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
                    <CardTitle>Combined History (Power & Rates)</CardTitle>
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
        const maxDiff = viewMode === "today" || viewMode === "tomorrow" ? 60000 : 3600000
        if (minDiff < maxDiff) {
            currentTimestamp = closestPoint
        }
    }

    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-col space-y-4 sm:flex-row sm:items-center sm:justify-between sm:space-y-0 pb-2">
                <div className="space-y-1">
                    <div className="flex items-center gap-3">
                        <CardTitle className="text-xl sm:text-2xl">Combined History</CardTitle>
                        {lastUpdate && (
                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                                systemStatus === "active"
                                    ? "bg-green-500/10 text-green-600 border border-green-500/20"
                                    : "bg-orange-500/10 text-orange-600 border border-orange-500/20"
                            }`}>
                                <div className={`w-1.5 h-1.5 rounded-full ${
                                    systemStatus === "active" ? "bg-green-500" : "bg-orange-500"
                                } animate-pulse`} />
                                <span>Updated {formatTimeAgo(lastUpdate)}</span>
                            </div>
                        )}
                    </div>
                    <CardDescription className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0">
                        <span>Total Consumption:</span>
                        <span className="hidden sm:inline text-muted-foreground mx-2">|</span>
                        <div className="flex gap-4 sm:gap-0">
                            <span className="text-blue-500 font-bold whitespace-nowrap">Peak: {totals.peak.toFixed(2)} kWh</span>
                            <span className="hidden sm:inline text-muted-foreground mx-2">|</span>
                            <span className="text-green-600 font-bold whitespace-nowrap">Off-Peak: {totals.offPeak.toFixed(2)} kWh</span>
                        </div>
                    </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button variant={viewMode === "today" ? "default" : "outline"} size="sm" onClick={() => setViewMode("today")}>Today</Button>
                    <Button variant={viewMode === "tomorrow" ? "default" : "outline"} size="sm" onClick={() => setViewMode("tomorrow")}>Tomorrow</Button>
                    <Button variant={viewMode === "7d" ? "default" : "outline"} size="sm" onClick={() => setViewMode("7d")}>7d</Button>
                    <Button variant={viewMode === "30d" ? "default" : "outline"} size="sm" onClick={() => setViewMode("30d")}>30d</Button>
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
                            {currentTimestamp && (viewMode === "today" || viewMode === "7d" || viewMode === "30d") && (() => {
                                // Find the index of the current timestamp in data array
                                const currentIndex = data.findIndex(d => d.timestamp === currentTimestamp.timestamp)

                                // Create a narrow band around the current time (use adjacent points for x1 and x2)
                                const x1 = currentIndex > 0 ? data[currentIndex - 1].timestamp : currentTimestamp.timestamp
                                const x2 = currentIndex < data.length - 1 ? data[currentIndex + 1].timestamp : currentTimestamp.timestamp

                                return (
                                    <ReferenceArea
                                        x1={x1}
                                        x2={x2}
                                        yAxisId="left"
                                        fill="#3b82f6"
                                        fillOpacity={0.15}
                                        stroke="#3b82f6"
                                        strokeWidth={2}
                                        strokeOpacity={0.5}
                                        label={{
                                            value: "NOW",
                                            position: "top",
                                            fill: "#3b82f6",
                                            fontSize: 11,
                                            fontWeight: 700
                                        }}
                                    />
                                )
                            })()}

                            <XAxis
                                dataKey="timestamp"
                                stroke="#888888"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                minTickGap={(viewMode === "today" || viewMode === "tomorrow") ? 30 : 60}
                            />
                            {/* Left Axis: Price */}
                            <YAxis
                                yAxisId="left"
                                stroke="#f050f8"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}p`}
                                label={{ value: 'Price (p/kWh)', angle: -90, position: 'insideLeft', fill: '#f050f8' }}
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
                                        const isSmart = props.payload.isSmart
                                        return [
                                            <div key="rate">
                                                <span>{Number(value).toFixed(2)}p</span>
                                                {isSmart && <span className="ml-2 text-green-400 font-bold">●</span>}
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
                                dot={<SmartDot />}
                                connectNulls
                            />

                            {/* Heater Lines (Right Axis) */}
                            <Line
                                yAxisId="right"
                                type="stepAfter"
                                dataKey="power_0"
                                name="Peak Heater (W)"
                                stroke="#2563eb"
                                connectNulls
                                strokeWidth={2}
                                dot={false}
                            />
                            <Line
                                yAxisId="right"
                                type="stepAfter"
                                dataKey="power_1"
                                name="Off-Peak Heater (W)"
                                stroke="#16a34a"
                                connectNulls
                                strokeWidth={2}
                                dot={false}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    )
}

