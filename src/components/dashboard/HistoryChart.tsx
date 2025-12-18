"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from "recharts"
import { Button } from "@/components/ui/button"

export function HistoryChart() {
    const [data, setData] = useState<any[]>([])
    const [days, setDays] = useState(1)

    useEffect(() => {
        const fetchHistory = async () => {
            const startDate = new Date()
            startDate.setDate(startDate.getDate() - days)

            const { data: readings } = await supabase
                .from("energy_readings")
                .select("*")
                .gte("created_at", startDate.toISOString())
                .order("created_at", { ascending: true })

            if (!readings) return

            // Transform for Recharts: Group by timestamp (approximate to minute?)
            // Or just map to flat list if channels have slightly diff timestamps?
            // Recharts needs unified X-Axis usually. 
            // Strategy: Create a combined dataset? 
            // Simpler: Just map rows. If channels are async, it handles it if we use 'type="monotone"' and separate lines?
            // Actually, Recharts wants array of objects.
            // Let's normalize to one array.

            const processed = readings.map(r => ({
                timestamp: new Date(r.created_at).toLocaleString(),
                raw_time: new Date(r.created_at).getTime(),
                [`power_${r.channel}`]: r.power_w,
                channel: r.channel
            }))

            setData(processed)
        }

        fetchHistory()
    }, [days])

    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Power Consumption History</CardTitle>
                <div className="flex space-x-2">
                    <Button variant={days === 1 ? "default" : "outline"} size="sm" onClick={() => setDays(1)}>24h</Button>
                    <Button variant={days === 7 ? "default" : "outline"} size="sm" onClick={() => setDays(7)}>7d</Button>
                    <Button variant={days === 30 ? "default" : "outline"} size="sm" onClick={() => setDays(30)}>30d</Button>
                </div>
            </CardHeader>
            <CardContent className="pl-2">
                <div className="h-[350px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis
                                dataKey="timestamp"
                                stroke="#888888"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                minTickGap={30}
                            />
                            <YAxis
                                stroke="#888888"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}W`}
                            />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1f2937", border: "none", color: "#fff" }}
                            />
                            <Legend />
                            {/* Note: If data is not perfectly aligned by timestamp, line might be jumpy. 
                  But for "power_0" (Main) and "power_1" (Second), 
                  we need to ensure 'connectNulls' or careful mapping.
                  Simplest: Render two lines, it will ignore undefined keys for that row.
              */}
                            <Line type="monotone" dataKey="power_0" name="Peak Heater" stroke="#2563eb" connectNulls strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="power_1" name="Off-Peak Heater" stroke="#16a34a" connectNulls strokeWidth={2} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    )
}
