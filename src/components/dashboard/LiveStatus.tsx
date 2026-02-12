"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, Activity, Flame } from "lucide-react"

interface Reading {
    device_id: string
    channel: number
    power_w: number
    voltage: number
    energy_total_wh: number
    created_at: string
}

// Separate components for each heater type to avoid dynamic class issues
function PeakHeaterCard({ power, voltage, energy, isOn, maxPower }: {
    power: number
    voltage: number
    energy: number
    isOn: boolean
    maxPower: number
}) {
    return (
        <Card className={`relative overflow-hidden transition-all duration-500 ${isOn ? "ring-2 ring-blue-500 shadow-lg shadow-blue-500/20" : ""
            }`}>
            {isOn && (
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-transparent animate-pulse" />
            )}

            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative">
                <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium">Heater 1 (Boost)</CardTitle>
                    {isOn ? (
                        <Badge className="bg-blue-500 hover:bg-blue-600 animate-pulse text-xs">
                            <Flame className="w-3 h-3 mr-1" />
                            ON
                        </Badge>
                    ) : (
                        <Badge variant="secondary" className="text-xs">OFF</Badge>
                    )}
                </div>
                <div className={`p-2 rounded-lg ${isOn ? "bg-blue-500 text-white" : "bg-muted"}`}>
                    <Zap className="h-4 w-4" />
                </div>
            </CardHeader>

            <CardContent className="relative">
                <div className="flex items-end gap-2">
                    <span className={`text-3xl font-bold tabular-nums ${isOn ? "text-blue-500" : ""}`}>
                        {power.toFixed(0)}
                    </span>
                    <span className="text-lg text-muted-foreground mb-1">W</span>
                </div>

                <div className="mt-3 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all duration-500 ${isOn ? "bg-gradient-to-r from-blue-400 to-blue-600" : "bg-muted-foreground/30"
                            }`}
                        style={{ width: `${Math.min((power / maxPower) * 100, 100)}%` }}
                    />
                </div>

                <p className="text-xs text-muted-foreground mt-2">
                    {voltage.toFixed(1)}V • {(energy / 1000).toFixed(1)} kWh total
                </p>
            </CardContent>
        </Card>
    )
}

function OffPeakHeaterCard({ power, voltage, energy, isOn, maxPower }: {
    power: number
    voltage: number
    energy: number
    isOn: boolean
    maxPower: number
}) {
    return (
        <Card className={`relative overflow-hidden transition-all duration-500 ${isOn ? "ring-2 ring-green-500 shadow-lg shadow-green-500/20" : ""
            }`}>
            {isOn && (
                <div className="absolute inset-0 bg-gradient-to-br from-green-500/10 to-transparent animate-pulse" />
            )}

            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative">
                <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium">Heater 2 (Storage)</CardTitle>
                    {isOn ? (
                        <Badge className="bg-green-500 hover:bg-green-600 animate-pulse text-xs">
                            <Flame className="w-3 h-3 mr-1" />
                            ON
                        </Badge>
                    ) : (
                        <Badge variant="secondary" className="text-xs">OFF</Badge>
                    )}
                </div>
                <div className={`p-2 rounded-lg ${isOn ? "bg-green-500 text-white" : "bg-muted"}`}>
                    <Activity className="h-4 w-4" />
                </div>
            </CardHeader>

            <CardContent className="relative">
                <div className="flex items-end gap-2">
                    <span className={`text-3xl font-bold tabular-nums ${isOn ? "text-green-500" : ""}`}>
                        {power.toFixed(0)}
                    </span>
                    <span className="text-lg text-muted-foreground mb-1">W</span>
                </div>

                <div className="mt-3 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all duration-500 ${isOn ? "bg-gradient-to-r from-green-400 to-green-600" : "bg-muted-foreground/30"
                            }`}
                        style={{ width: `${Math.min((power / maxPower) * 100, 100)}%` }}
                    />
                </div>

                <p className="text-xs text-muted-foreground mt-2">
                    {voltage.toFixed(1)}V • {(energy / 1000).toFixed(1)} kWh total
                </p>
            </CardContent>
        </Card>
    )
}

export function LiveStatus() {
    const [readings, setReadings] = useState<Reading[]>([])
    const [loading, setLoading] = useState(true)
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

    const fetchLive = async () => {
        // Fetch latest reading for each channel separately
        const [channel0Response, channel1Response] = await Promise.all([
            supabase
                .from("energy_readings")
                .select("*")
                .eq("channel", 0)
                .order("created_at", { ascending: false })
                .limit(1),
            supabase
                .from("energy_readings")
                .select("*")
                .eq("channel", 1)
                .order("created_at", { ascending: false })
                .limit(1)
        ])

        const combinedData = [
            ...(channel0Response.data || []),
            ...(channel1Response.data || [])
        ]

        if (combinedData.length > 0) {
            setReadings(combinedData)
            // Use the most recent timestamp from either channel
            const latestTimestamp = Math.max(
                ...combinedData.map(r => new Date(r.created_at).getTime())
            )
            setLastUpdated(new Date(latestTimestamp))
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

    // Data ingestion runs every 10 minutes via GitHub Actions
    // Show offline if no data for 15 minutes (10 min schedule + 5 min buffer)
    const isOnline = lastUpdated && (new Date().getTime() - lastUpdated.getTime()) < 15 * 60 * 1000

    // Calculate minutes since last update for display
    const minutesSinceUpdate = lastUpdated
        ? Math.floor((new Date().getTime() - lastUpdated.getTime()) / 60000)
        : null

    // Determine if heaters are ON (power > 100W threshold)
    // FORCE OFF if system is offline (stale data > 15 mins)
    const isPeakOn = (isOnline ?? false) && (main?.power_w ?? 0) > 100
    const isOffPeakOn = (isOnline ?? false) && (second?.power_w ?? 0) > 100

    // Max power for progress bar (3kW heaters)
    const MAX_POWER = 3200

    return (
        <div className="space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <h2 className="text-2xl font-bold tracking-tight">Heater Status (Live)</h2>
                <div className="flex items-center space-x-2 w-full sm:w-auto justify-between sm:justify-end">
                    <Badge
                        variant={isOnline ? "default" : "destructive"}
                        className={isOnline ? "bg-green-500 hover:bg-green-600" : ""}
                    >
                        <span className={`w-2 h-2 rounded-full mr-2 ${isOnline ? "bg-white animate-pulse" : "bg-red-200"}`} />
                        {isOnline ? "System Online" : "Offline"}
                    </Badge>
                    {lastUpdated && (
                        <span className="text-sm text-muted-foreground">
                            {minutesSinceUpdate === 0
                                ? "Updated just now"
                                : minutesSinceUpdate === 1
                                    ? "1 min ago"
                                    : `${minutesSinceUpdate} mins ago`}
                        </span>
                    )}
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
                <PeakHeaterCard
                    power={(isOnline ?? false) ? (main?.power_w ?? 0) : 0}
                    voltage={main?.voltage ?? 0}
                    energy={main?.energy_total_wh ?? 0}
                    isOn={isPeakOn}
                    maxPower={MAX_POWER}
                />
                <OffPeakHeaterCard
                    power={(isOnline ?? false) ? (second?.power_w ?? 0) : 0}
                    voltage={second?.voltage ?? 0}
                    energy={second?.energy_total_wh ?? 0}
                    isOn={isOffPeakOn}
                    maxPower={MAX_POWER}
                />
            </div>
        </div>
    )
}


