"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { isHistoricalCalendarDate } from "@/lib/date-selection"
import { getUKDateString } from "@/lib/date-utils"

interface PaidPriceWindow {
    avg_paid_ppkwh: number | null
    total_kwh_priced: number
    total_kwh_measured: number
}

interface EnergyStatsResponse {
    yesterday: PaidPriceWindow
    last7d: PaidPriceWindow
    last30d: PaidPriceWindow
    selected_day: {
        date: string
        window: PaidPriceWindow
    } | null
}

function formatDateLabel(dateStr: string): string {
    const [year, month, day] = dateStr.split("-")
    if (!year || !month || !day) {
        return dateStr
    }
    return `${day}/${month}/${year}`
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
    const searchParams = useSearchParams()
    const selectedDateRaw = searchParams.get("selectedDate")
    const selectedDate = isHistoricalCalendarDate(selectedDateRaw, getUKDateString(-1))
        ? selectedDateRaw
        : null
    const [stats, setStats] = useState<EnergyStatsResponse | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const controller = new AbortController()

        const fetchStats = async () => {
            setLoading(true)
            try {
                const query = selectedDate ? `?selectedDate=${encodeURIComponent(selectedDate)}` : ""
                const response = await fetch(`/api/energy-stats${query}`, {
                    cache: "no-store",
                    signal: controller.signal,
                })
                if (controller.signal.aborted) return
                if (response.ok) {
                    const data: EnergyStatsResponse = await response.json()
                    if (controller.signal.aborted) return
                    setStats(data)
                } else {
                    setStats(null)
                }
            } catch (error) {
                if (controller.signal.aborted) return
                console.error("Failed to fetch paid price insights:", error)
                setStats(null)
            } finally {
                if (!controller.signal.aborted) setLoading(false)
            }
        }

        fetchStats()
        const interval = setInterval(fetchStats, 5 * 60 * 1000)
        return () => {
            controller.abort()
            clearInterval(interval)
        }
    }, [selectedDate])

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="text-xl">Average Price You Paid (Heaters)</CardTitle>
                <CardDescription>
                    kWh-weighted unit price using actual heater consumption and Agile tariff intervals.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {stats?.selected_day && (
                        <div className="rounded-lg border bg-card p-4">
                            <p className="text-sm text-muted-foreground">Selected ({formatDateLabel(stats.selected_day.date)})</p>
                            <p className="text-2xl font-semibold mt-1">
                                {loading ? "…" : formatWindowValue(stats.selected_day.window)}
                            </p>
                        </div>
                    )}
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
