"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
    const [viewMode, setViewMode] = useState<"today" | "7d" | "30d">("today")

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

            const ratesPromise = fetch(
                `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?period_from=${startIso}&page_size=1500`
            ).then(r => r.json())

            const readingsPromise = supabase
                .from("energy_readings")
                .select("*")
                .gte("created_at", startIso)
                .lte("created_at", endIso) // Limit to end of today to avoid next-day leakage if any
                .order("created_at", { ascending: true })

            try {
                const [rData, sData] = await Promise.all([ratesPromise, readingsPromise])
                if (rData.results) rates = rData.results
                if (sData.data) readings = sData.data
            } catch (e) {
                console.error("Fetch error", e)
            }

            // 3. Build Unified Buckets (30 mins)
            // We iterate from start to end in 30 min steps.
            const buckets = []
            const currentCursor = new Date(startDate)

            // Pre-process readings into a Map for faster lookup? 
            // Or just filter? Filtering inside loop is O(N*M). Grouping is O(N).
            // Let's bucket readings by 30-min slot key.
            const readingsBySlot = new Map<number, any[]>()
            readings.forEach(r => {
                const t = new Date(r.created_at)
                // Round down to nearest 30 min
                const remainder = t.getMinutes() % 30
                t.setMinutes(t.getMinutes() - remainder, 0, 0)
                const key = t.getTime()
                if (!readingsBySlot.has(key)) readingsBySlot.set(key, [])
                readingsBySlot.get(key)?.push(r)
            })

            // Sort rates for lookup
            rates.sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())

            while (currentCursor <= endDate) {
                const timestamp = currentCursor.toLocaleString([], {
                    month: viewMode === "today" ? undefined : 'numeric',
                    day: viewMode === "today" ? undefined : 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                })
                const slotTime = currentCursor.getTime()

                // Find Rate
                // Rate is valid if valid_from <= slotTime < valid_to
                const rateObj = rates.find(r => {
                    const from = new Date(r.valid_from).getTime()
                    const to = new Date(r.valid_to).getTime()
                    return slotTime >= from && slotTime < to
                })

                // Find Power (Average in this slot)
                const slotReadings = readingsBySlot.get(slotTime) || []

                // Calculate Avg Power for Channel 0 and 1
                const p0_vals = slotReadings.filter(r => r.channel === 0).map(r => r.power_w)
                const p1_vals = slotReadings.filter(r => r.channel === 1).map(r => r.power_w)

                const avg0 = p0_vals.length > 0 ? p0_vals.reduce((a, b) => a + b, 0) / p0_vals.length : null
                const avg1 = p1_vals.length > 0 ? p1_vals.reduce((a, b) => a + b, 0) / p1_vals.length : null

                // For "Today", we want to show the full day (including future).
                // Future power will be null (correct).
                // Future rates will be present (correct).

                buckets.push({
                    timestamp,
                    raw_time: slotTime,
                    rate: rateObj ? rateObj.value_inc_vat : null,
                    power_0: avg0, // Peak Heater (Main/Daily) -> Wait, check names!
                    // Last check: 0=Peak(Negative), 1=Off-Peak(Daily). 
                    // Let's use generic names here and let Legend handle it? 
                    // No, chart needs labels.
                    // 0 = Peak Heater (Negative)
                    // 1 = Off-Peak Heater (Daily)
                    power_1: avg1
                })

                // Step 30 mins
                currentCursor.setMinutes(currentCursor.getMinutes() + 30)
            }

            setData(buckets)
        }

        fetchData()
    }, [viewMode])

    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Combined History (Power & Rates)</CardTitle>
                <div className="flex space-x-2">
                    <Button variant={viewMode === "today" ? "default" : "outline"} size="sm" onClick={() => setViewMode("today")}>Today</Button>
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
                                minTickGap={viewMode === "today" ? 30 : 60}
                            />
                            {/* Left Axis: Price */}
                            <YAxis
                                yAxisId="left"
                                stroke="#8884d8"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}p`}
                                label={{ value: 'Price (p/kWh)', angle: -90, position: 'insideLeft', fill: '#8884d8' }}
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
                            />
                            <Legend />

                            {/* Rate Line (Left Axis) */}
                            <Line
                                yAxisId="left"
                                type="stepAfter"
                                dataKey="rate"
                                name="Rate (p/kWh)"
                                stroke="#8884d8"
                                strokeWidth={2}
                                dot={false}
                                connectNulls
                            />

                            {/* Heater Lines (Right Axis) */}
                            <Line
                                yAxisId="right"
                                type="monotone"
                                dataKey="power_0"
                                name="Peak Heater (W)"
                                stroke="#2563eb"
                                connectNulls
                                strokeWidth={2}
                                dot={false}
                            />
                            <Line
                                yAxisId="right"
                                type="monotone"
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
