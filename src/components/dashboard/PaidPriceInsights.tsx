"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { isHistoricalCalendarDate } from "@/lib/date-selection"
import { getUKDateString } from "@/lib/date-utils"
import { Sparkles } from "lucide-react"

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

    const windows: Array<{ label: string; window: PaidPriceWindow | null | undefined }> = [
        ...(stats?.selected_day
            ? [{ label: `Selected (${formatDateLabel(stats.selected_day.date)})`, window: stats.selected_day.window }]
            : []),
        { label: "Yesterday", window: stats?.yesterday },
        { label: "Last 7 Days", window: stats?.last7d },
        { label: "Last 30 Days", window: stats?.last30d },
    ]

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="font-display text-xl font-extrabold">Average Price You Paid (Heaters)</CardTitle>
                <CardDescription>
                    kWh-weighted unit price using actual heater consumption and Agile tariff intervals.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {windows.map(({ label, window }) => {
                        const earning = window?.avg_paid_ppkwh != null && window.avg_paid_ppkwh <= 0
                        return (
                            <div
                                key={label}
                                className={`rounded-lg border p-4 ${earning ? "border-live/40 bg-live/10" : "border-border/60 bg-secondary/50"}`}
                            >
                                <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                                <p className={`text-2xl font-bold mt-1 font-mono tabular-nums ${earning ? "text-live" : "text-rust"}`}>
                                    {loading ? "…" : formatWindowValue(window)}
                                </p>
                                {earning && !loading && (
                                    <p className="mt-1 flex items-center gap-1 text-xs font-medium text-live">
                                        <Sparkles className="w-3 h-3" />
                                        You got paid to heat
                                    </p>
                                )}
                            </div>
                        )
                    })}
                </div>
            </CardContent>
        </Card>
    )
}
