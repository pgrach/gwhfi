"use client"

import { useEffect, useState } from "react"
import { createClient } from "@supabase/supabase-js" // direct import or use lib usage? lib usage is cleaner. 
// But context/provider is overkill for simple. I'll use lib/supabase.

import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, Activity, Clock } from "lucide-react"

interface Reading {
    device_id: string
    channel: number
    power_w: number
    voltage: number
    energy_total_wh: number
    created_at: string
}

export function LiveStatus() {
    const [readings, setReadings] = useState<Reading[]>([])
    const [loading, setLoading] = useState(true)
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

    const fetchLive = async () => {
        const { data, error } = await supabase
            .from("energy_readings")
            .select("*")
            .order("created_at", { ascending: false })
            .limit(2)

        if (data) {
            setReadings(data)
            if (data.length > 0) {
                setLastUpdated(new Date(data[0].created_at))
            }
        }
        setLoading(false)
    }

    useEffect(() => {
        fetchLive()
        const interval = setInterval(fetchLive, 5000)
        return () => clearInterval(interval)
    }, [])

    const main = readings.find(r => r.channel === 0)
    const second = readings.find(r => r.channel === 1)

    const isOnline = lastUpdated && (new Date().getTime() - lastUpdated.getTime()) < 5 * 60 * 1000 // 5 mins

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold tracking-tight">Live Status</h2>
                <div className="flex items-center space-x-2">
                    <Badge variant={isOnline ? "default" : "destructive"}>
                        {isOnline ? "System Online" : "Offline"}
                    </Badge>
                    {lastUpdated && <span className="text-sm text-muted-foreground">{lastUpdated.toLocaleTimeString()}</span>}
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2">
                {/* Main Heater */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Main Heater</CardTitle>
                        <Zap className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{main?.power_w.toFixed(0) ?? 0} W</div>
                        <p className="text-xs text-muted-foreground">
                            {main?.voltage.toFixed(1) ?? 0} V | {(main?.energy_total_wh ?? 0 / 1000).toFixed(1)} kWh
                        </p>
                    </CardContent>
                </Card>

                {/* Second Heater */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Second Heater</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{second?.power_w.toFixed(0) ?? 0} W</div>
                        <p className="text-xs text-muted-foreground">
                            {second?.voltage.toFixed(1) ?? 0} V | {(second?.energy_total_wh ?? 0 / 1000).toFixed(1)} kWh
                        </p>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
