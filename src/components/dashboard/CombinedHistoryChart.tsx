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
    ResponsiveContainer
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
            // For tomorrow view, we need period_from to be robust.
            // Actually, querying from startDate (which might be tomorrow) is fine.
            const ratesPromise = fetch(
                `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?period_from=${startIso}&page_size=1500`
            ).then(r => r.json())

            // Note: We need energy_total_wh for accurate consumption
            const readingsPromise = supabase
                .from("energy_readings")
                .select("*")
                .gte("created_at", startIso)
                .lte("created_at", endIso)
                .order("created_at", { ascending: true })

            try {
                const [rData, sData] = await Promise.all([ratesPromise, readingsPromise])
                if (rData.results) {
                    rates = rData.results
                    // Check if we actually got rates for the requested period
                    if (rates.length === 0 && viewMode === "tomorrow") {
                        setHasRates(false)
                    } else {
                        setHasRates(true)
                    }
                }
                if (sData.data) readings = sData.data
            } catch (e) {
                console.error("Fetch error", e)
                setHasRates(false)
            }

            // --- Calculate Totals (kWh) ---
            // Robust calculation: sum of positive deltas to handle counter resets
            const calculateKWh = (channelId: number) => {
                const channelReadings = readings.filter(r => r.channel === channelId)
                if (channelReadings.length < 2) return 0

                // Simple Max - Min method (assuming no resets for now as it's cleaner for short periods)
                // If we want to be robust against resets:
                let totalWh = 0
                for (let i = 1; i < channelReadings.length; i++) {
                    const prev = channelReadings[i - 1].energy_total_wh
                    const curr = channelReadings[i].energy_total_wh
                    // Only add if monotonic increase, handle reset (curr < prev) by assuming curr is new accumulation
                    if (curr >= prev) {
                        totalWh += (curr - prev)
                    } else {
                        // Counter reset
                        totalWh += curr
                    }
                }
                return totalWh / 1000 // Convert to kWh
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
            // Today/Tomorrow = 1 min (Max resolution)
            // History = 30 mins (Performance)
            const bucketMinutes = (viewMode === "today" || viewMode === "tomorrow") ? 1 : 30

            const buckets = []
            const currentCursor = new Date(startDate)

            const readingsBySlot = new Map<number, any[]>()
            readings.forEach(r => {
                const t = new Date(r.created_at)
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

                // Determine if Smart Slot (Lookup from pre-calculated map)
                // We key by rateObj.valid_from time
                let isSmart = false
                if (rateObj) {
                    const rateTime = new Date(rateObj.valid_from).getTime()
                    isSmart = smartMap.get(rateTime) || false
                }

                const slotReadings = readingsBySlot.get(slotTime) || []
                const p0_vals = slotReadings.filter(r => r.channel === 0).map(r => r.power_w)
                const p1_vals = slotReadings.filter(r => r.channel === 1).map(r => r.power_w)

                const avg0 = p0_vals.length > 0 ? p0_vals.reduce((a, b) => a + b, 0) / p0_vals.length : null
                const avg1 = p1_vals.length > 0 ? p1_vals.reduce((a, b) => a + b, 0) / p1_vals.length : null

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

    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <div className="space-y-1">
                    <CardTitle>Combined History (Power & Rates)</CardTitle>
                    <CardDescription>
                        Total Consumption:
                        <span className="text-blue-500 font-bold ml-2">Peak: {totals.peak.toFixed(2)} kWh</span>
                        <span className="text-muted-foreground mx-2">|</span>
                        <span className="text-green-600 font-bold">Off-Peak: {totals.offPeak.toFixed(2)} kWh</span>
                    </CardDescription>
                </div>
                <div className="flex space-x-2">
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

