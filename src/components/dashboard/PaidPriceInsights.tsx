"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

interface PaidPriceWindow {
    avg_paid_ppkwh: number | null
    total_kwh_priced: number
    total_kwh_measured: number
}

interface EnergyStatsResponse {
    yesterday: PaidPriceWindow
    last7d: PaidPriceWindow
    last30d: PaidPriceWindow
}

function formatWindowValue(window: PaidPriceWindow | null | undefined): string {
    if (!window) {
        return "—"
    }
    if (window.avg_paid_ppkwh != null) {
        return `${window.avg_paid_ppkwh.toFixed(2)}p/kWh`
    }
    if (window.total_kwh_measured <= 0) {
        return "No usage"
    }
    if (window.total_kwh_priced <= 0) {
        return "No priced data"
    }
    return "—"
}

export function PaidPriceInsights() {
    const [stats, setStats] = useState<EnergyStatsResponse | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const response = await fetch("/api/energy-stats", { cache: "no-store" })
                if (response.ok) {
                    const data: EnergyStatsResponse = await response.json()
                    setStats(data)
                }
            } catch (error) {
                console.error("Failed to fetch paid price insights:", error)
            } finally {
                setLoading(false)
            }
        }

        fetchStats()
        const interval = setInterval(fetchStats, 5 * 60 * 1000)
        return () => clearInterval(interval)
    }, [])

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="text-xl">Average Price You Paid (Heaters)</CardTitle>
                <CardDescription>
                    kWh-weighted unit price using actual heater consumption and Agile tariff intervals.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid gap-3 sm:grid-cols-3">
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Yesterday</p>
                        <p className="text-2xl font-semibold mt-1">
                            {loading ? "…" : formatWindowValue(stats?.yesterday)}
                        </p>
                    </div>
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Last 7 Days</p>
                        <p className="text-2xl font-semibold mt-1">
                            {loading ? "…" : formatWindowValue(stats?.last7d)}
                        </p>
                    </div>
                    <div className="rounded-lg border bg-card p-4">
                        <p className="text-sm text-muted-foreground">Last 30 Days</p>
                        <p className="text-2xl font-semibold mt-1">
                            {loading ? "…" : formatWindowValue(stats?.last30d)}
                        </p>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
