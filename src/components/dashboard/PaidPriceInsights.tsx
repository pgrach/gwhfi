"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { isHistoricalCalendarDate } from "@/lib/date-selection"
import { getUKDateString } from "@/lib/date-utils"
import { CircleAlert, Info, Sparkles } from "lucide-react"

type StorageSavingsStatus = "available" | "no_usage" | "insufficient_data" | "not_applicable"

interface StorageSavingsBaseline {
    start: string
    end: string
    sample_days: number
    excluded_local_window: string
}

interface StorageSavings {
    status: StorageSavingsStatus
    actual_avg_ppkwh: number | null
    saved_gbp: number | null
    baseline: StorageSavingsBaseline | null
}

interface PaidPriceWindow {
    storage_savings: StorageSavings
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

interface SavingsTileProps {
    label: string
    window: PaidPriceWindow | null | undefined
    loading: boolean
}

function formatDateLabel(dateStr: string): string {
    const [year, month, day] = dateStr.split("-")
    if (!year || !month || !day) {
        return dateStr
    }
    return `${day}/${month}/${year}`
}

function isFiniteMetric(value: number | null | undefined): value is number {
    return typeof value === "number" && Number.isFinite(value)
}

function formatRate(value: number): string {
    return `${value.toFixed(2)}p/kWh`
}

function formatMoney(value: number): string {
    const sign = value < 0 ? "-" : ""
    return `${sign}£${Math.abs(value).toFixed(2)}`
}

function SavingsTile({ label, window, loading }: SavingsTileProps) {
    const savings = window?.storage_savings

    if (loading) {
        return (
            <div className="min-h-40 rounded-lg border border-border/60 bg-secondary/50 p-4" aria-busy="true">
                <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                <p className="mt-5 text-sm text-muted-foreground" aria-live="polite">Loading savings…</p>
            </div>
        )
    }

    if (!savings) {
        return (
            <div className="min-h-40 rounded-lg border border-border/60 bg-secondary/50 p-4">
                <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                <p className="mt-5 flex items-center gap-2 text-sm font-semibold text-foreground">
                    <CircleAlert className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                    Data unavailable
                </p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    Storage-heater savings could not be loaded for this period.
                </p>
            </div>
        )
    }

    if (savings.status === "no_usage") {
        return (
            <div className="min-h-40 rounded-lg border border-border/60 bg-secondary/50 p-4">
                <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                <p className="mt-5 text-lg font-bold text-foreground">No storage-heater usage</p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    No savings estimate is shown because no storage-heater energy was measured.
                </p>
            </div>
        )
    }

    if (savings.status === "not_applicable") {
        return (
            <div className="min-h-40 rounded-lg border border-border/60 bg-secondary/50 p-4">
                <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                <p className="mt-5 text-lg font-bold text-foreground">Smart control not active</p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    This period predates Heat21 storage-heater scheduling, so no algorithm savings are claimed.
                </p>
            </div>
        )
    }

    const actualRate = savings.actual_avg_ppkwh
    const savedGbp = savings.saved_gbp
    const hasActualRate = isFiniteMetric(actualRate)

    if (
        savings.status !== "available"
        || !hasActualRate
        || !isFiniteMetric(savedGbp)
    ) {
        return (
            <div className="min-h-40 rounded-lg border border-border/60 bg-secondary/50 p-4">
                <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                {hasActualRate && (
                    <div className="mt-4">
                        <p className="text-[11px] font-medium text-muted-foreground">Average tariff achieved</p>
                        <p className={`mt-1 font-mono text-xl font-bold tabular-nums ${actualRate <= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rust"}`}>
                            {formatRate(actualRate)}
                        </p>
                    </div>
                )}
                <p className="mt-5 flex items-center gap-2 text-sm font-semibold text-foreground">
                    <CircleAlert className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                    Savings estimate unavailable
                </p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    There is not enough verified baseline or tariff coverage for this period.
                </p>
            </div>
        )
    }

    const positiveSaving = savedGbp > 0
    const negativeSaving = savedGbp < 0
    const savingTone = positiveSaving
        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
        : negativeSaving
            ? "border-destructive/30 bg-destructive/10 text-destructive"
            : "border-border/60 bg-background/50 text-foreground"

    return (
        <div className="min-h-48 rounded-lg border border-border/60 bg-secondary/50 p-4">
            <p className="text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>

            <div className="mt-4">
                <p className="text-[11px] font-medium text-muted-foreground">Average tariff achieved</p>
                <p className={`mt-1 font-mono text-2xl font-bold tabular-nums ${actualRate <= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rust"}`}>
                    {formatRate(actualRate)}
                </p>
            </div>

            <div className={`mt-4 rounded-md border px-4 py-3 ${savingTone}`}>
                <p className="text-[11px] font-medium uppercase tracking-[0.08em]">
                    {negativeSaving ? "Estimated difference" : "Estimated saving"}
                </p>
                <p
                    className="mt-1 flex items-center gap-1.5 font-mono text-2xl font-extrabold tabular-nums"
                    aria-label={negativeSaving
                        ? `Estimated cost ${formatMoney(Math.abs(savedGbp))} higher than the estimate without smart control`
                        : `Estimated savings ${formatMoney(savedGbp)}`}
                >
                    {positiveSaving && <Sparkles className="h-4 w-4 shrink-0" aria-hidden="true" />}
                    {negativeSaving
                        ? `Cost ${formatMoney(Math.abs(savedGbp))} more`
                        : positiveSaving
                            ? `Saved ${formatMoney(savedGbp)}`
                            : "No cost difference"}
                </p>
                <p className="mt-1 text-[11px] font-medium">
                    Versus estimated operation without smart control
                </p>
            </div>
        </div>
    )
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
                console.error("Failed to fetch storage-heater savings:", error)
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
    const baseline = windows
        .map(({ window }) => window?.storage_savings?.baseline)
        .find((candidate): candidate is StorageSavingsBaseline => candidate != null)

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="font-display text-xl font-extrabold">Storage-Heater Tariff &amp; Estimated Savings</CardTitle>
                <CardDescription>
                    The average tariff achieved through smart timing, plus one estimated cost difference.
                </CardDescription>
                <details className="group mt-1 rounded-md border border-border/60 bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
                    <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                        <Info className="h-3.5 w-3.5" aria-hidden="true" />
                        How the estimate works
                    </summary>
                    <div className="mt-2 space-y-1.5 leading-relaxed">
                        <p>
                            Estimated pounds saved reprice the same measured storage-heater kWh using the verified pre-smart timing pattern, with the 16:00–19:00 timer cutoff retained. We do not claim reduced energy use.
                        </p>
                        {baseline && (
                            <p>
                                Historical baseline: {baseline.sample_days} verified day{baseline.sample_days === 1 ? "" : "s"}, {formatDateLabel(baseline.start)}–{formatDateLabel(baseline.end)}, retaining the {baseline.excluded_local_window} timer cutoff.
                            </p>
                        )}
                    </div>
                </details>
            </CardHeader>
            <CardContent>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {windows.map(({ label, window }) => (
                        <SavingsTile key={label} label={label} window={window} loading={loading} />
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}
