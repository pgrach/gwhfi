"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
    ComposedChart,
    Area,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceArea,
    ReferenceLine,
} from "recharts"
import { getUKDateBoundaries, getUKDateBoundariesForDate, getUKDateString } from "@/lib/date-utils"
import {
    calendarValueForView,
    classifyDateSelection,
    EARLIEST_DASHBOARD_DATE,
    isHistoricalCalendarDate,
    isValidCalendarDate,
    resolveDateView,
    type DateViewMode,
} from "@/lib/date-selection"
import { OCTOPUS_RATES_URL } from "@/lib/octopus-config"
import { bridgeSingleBucketGaps, collectScheduledPeriods } from "@/lib/power-series"
import {
    buildDownsampledReadingsRequest,
    PUBLIC_METER_DEVICE_ID,
    PUBLIC_TELEMETRY_SITE_ID,
    siteOrLegacyFilter,
} from "@/lib/telemetry-scope"
import { fetchCompleteDownsampledRange } from "@/lib/downsampled-readings"

interface Rate {
    value_inc_vat: number
    valid_from: string
    valid_to: string
}

interface ScheduleSlot {
    slot_start: string
    slot_end: string
    price: number
    heater_type: string
}

interface DownsampledReading {
    bucket_time: string
    channel: number
    avg_power: number | null
}

interface CounterReading {
    device_id: string
    energy_total_wh: number | null
    created_at: string
}

interface CounterPoint {
    deviceId: string
    wattHours: number
    timestampMs: number
}

interface ChartPoint {
    raw_time: number
    rate: number | null
    isScheduled: boolean
    power_0: number | null
    power_1: number | null
}

function asCounterPoint(reading: CounterReading | undefined): CounterPoint | null {
    if (!reading) return null

    if (reading.energy_total_wh === null) return null

    const wattHours = Number(reading.energy_total_wh)
    const timestampMs = Date.parse(reading.created_at)
    if (!reading.device_id || !Number.isFinite(wattHours) || !Number.isFinite(timestampMs)) {
        return null
    }

    return { deviceId: reading.device_id, wattHours, timestampMs }
}

function interpolateCounterAt(
    beforeReading: CounterReading | undefined,
    afterReading: CounterReading | undefined,
    boundaryMs: number,
): CounterPoint | null {
    const before = asCounterPoint(beforeReading)
    const after = asCounterPoint(afterReading)

    if (before?.timestampMs === boundaryMs) return before
    if (after?.timestampMs === boundaryMs) return after
    if (!before || !after
        || before.deviceId !== after.deviceId
        || before.timestampMs >= after.timestampMs
        || before.timestampMs > boundaryMs
        || after.timestampMs < boundaryMs
        || before.wattHours > after.wattHours) {
        return null
    }

    const elapsedRatio = (boundaryMs - before.timestampMs) / (after.timestampMs - before.timestampMs)
    return {
        deviceId: before.deviceId,
        wattHours: before.wattHours + ((after.wattHours - before.wattHours) * elapsedRatio),
        timestampMs: boundaryMs,
    }
}

export function CombinedHistoryChart() {
    const router = useRouter()
    const pathname = usePathname()
    const searchParams = useSearchParams()
    const selectedDateParam = searchParams.get("selectedDate")
    const requestedViewParam = searchParams.get("view")
    const currentQuery = searchParams.toString()
    const ukToday = getUKDateString(0)
    const ukTomorrow = getUKDateString(1)
    const ukYesterday = getUKDateString(-1)
    const resolvedDateView = resolveDateView(selectedDateParam, requestedViewParam, ukToday, ukTomorrow)
    const viewMode = resolvedDateView.viewMode
    const customDate = resolvedDateView.customDate ?? ukYesterday

    const [data, setData] = useState<ChartPoint[]>([])
    const [hasRates, setHasRates] = useState(true)
    const [totals, setTotals] = useState<{ peak: number | null; offPeak: number | null }>({
        peak: null,
        offPeak: null,
    })
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
    const [telemetryState, setTelemetryState] = useState<"loading" | "ok" | "empty" | "error">("loading")
    const [nowMs, setNowMs] = useState(() => Date.now())
    const [refreshKey, setRefreshKey] = useState(0)

    const navigateToDateView = (nextView: DateViewMode, date?: string) => {
        const params = new URLSearchParams(currentQuery)
        params.delete("selectedDate")
        params.delete("view")

        if (nextView === "custom" && date) {
            params.set("selectedDate", date)
        } else if (nextView !== "today") {
            params.set("view", nextView)
        }

        const query = params.toString()
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
    }

    useEffect(() => {
        const params = new URLSearchParams(currentQuery)
        let canonicalDate: string | null = null
        let canonicalView: "tomorrow" | "7d" | "30d" | null = null

        if (isHistoricalCalendarDate(selectedDateParam, ukYesterday)) {
            canonicalDate = selectedDateParam
        } else if (selectedDateParam === ukTomorrow) {
            canonicalView = "tomorrow"
        } else if (selectedDateParam !== ukToday) {
            if (requestedViewParam === "tomorrow" || requestedViewParam === "7d" || requestedViewParam === "30d") {
                canonicalView = requestedViewParam
            }
        }

        if (canonicalDate) params.set("selectedDate", canonicalDate)
        else params.delete("selectedDate")

        if (canonicalView) params.set("view", canonicalView)
        else params.delete("view")

        if (params.toString() === currentQuery) return

        const query = params.toString()
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
    }, [currentQuery, pathname, requestedViewParam, router, selectedDateParam, ukToday, ukTomorrow, ukYesterday])

    useEffect(() => {
        const clockInterval = window.setInterval(() => setNowMs(Date.now()), 30_000)
        const refreshInterval = window.setInterval(() => setRefreshKey((value) => value + 1), 5 * 60_000)

        return () => {
            window.clearInterval(clockInterval)
            window.clearInterval(refreshInterval)
        }
    }, [])

    useEffect(() => {
        let cancelled = false

        const fetchData = async () => {
            setTelemetryState("loading")

            // 1. Define Timeline Boundaries (always in UK time)
            let startDate: Date
            let endDate: Date

            if (viewMode === "today") {
                const { start, end } = getUKDateBoundaries(0)
                startDate = start
                endDate = end
            } else if (viewMode === "tomorrow") {
                const { start, end } = getUKDateBoundaries(1)
                startDate = start
                endDate = end
            } else if (viewMode === "7d") {
                const { start } = getUKDateBoundaries(-6)
                const { end } = getUKDateBoundaries(0)
                startDate = start
                endDate = end
            } else if (viewMode === "custom") {
                try {
                    const { start, end } = getUKDateBoundariesForDate(customDate)
                    startDate = start
                    endDate = end
                } catch {
                    const { start, end } = getUKDateBoundariesForDate(ukYesterday)
                    startDate = start
                    endDate = end
                }
            } else {
                // 30d
                const { start } = getUKDateBoundaries(-29)
                const { end } = getUKDateBoundaries(0)
                startDate = start
                endDate = end
            }

            const startIso = startDate.toISOString()
            const endIso = endDate.toISOString()

            // 2. Fetch Data
            let rates: Rate[] = []
            let readings: DownsampledReading[] = []
            let scheduleSlots: ScheduleSlot[] = []
            let readingsFetchFailed = false
            let channelTotals = new Map<number, number | null>([
                [0, null],
                [1, null],
            ])

            // Explicitly ensure we fetch enough future data if viewing tomorrow
            const ratesPromise = fetch(
                `${OCTOPUS_RATES_URL}?period_from=${startIso}&period_to=${endIso}&page_size=2000`
            ).then(r => r.json())

            // Define bucket size based on view mode
            // Today/Tomorrow = 1 min (Raw data)
            // 7d = 1 hour (Aggregated)
            // 30d = 1 hour (Aggregated) or maybe 4 hours? Let's try 1h first.
            // ALWAYS use RPC downsampling to avoid Supabase's 1000-row limit
            const bucketMinutes = (viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom") ? 1 : 60

            const fetchReadingsChunk = (chunkStartIso: string, chunkEndIso: string) => {
                const request = buildDownsampledReadingsRequest(
                    chunkStartIso,
                    chunkEndIso,
                    bucketMinutes * 60,
                    PUBLIC_METER_DEVICE_ID,
                    PUBLIC_TELEMETRY_SITE_ID,
                )
                return supabase.rpc(request.functionName, request.params)
            }

            // Each bucket can return both channels, so even one day of minute
            // telemetry exceeds Supabase's 1000-row response limit. Fetch in
            // bounded time slices and recursively split any response that still
            // reaches the cap. The helper also de-duplicates inclusive legacy
            // RPC boundaries and restores chronological order.
            const readingsPromise: Promise<DownsampledReading[]> = (async () => {
                const result = await fetchCompleteDownsampledRange<DownsampledReading>(
                    startDate.getTime(),
                    endDate.getTime(),
                    bucketMinutes * 60,
                    async (chunkStartIso, chunkEndIso) => {
                        const response = await fetchReadingsChunk(chunkStartIso, chunkEndIso)
                        return {
                            data: response.data as DownsampledReading[] | null,
                            error: response.error,
                        }
                    },
                )

                if (result.errors.length > 0) {
                    readingsFetchFailed = true
                    result.errors.forEach((error, index) => {
                        console.error(`Supabase telemetry error (chunk ${index + 1}):`, error)
                    })
                }
                return result.data
            })()

            // Fetch only the off-peak schedule that drives the storage heater.
            const schedulePromise = supabase
                .from('heating_schedule')
                .select('*')
                .eq('heater_type', 'off_peak')
                .lte('slot_start', endIso)
                .gt('slot_end', startIso)
                .order('slot_start', { ascending: true })

            // Cumulative meter counters are the source of truth for energy usage.
            // Average power is useful for the chart, but summing fixed-size buckets
            // overstates usage when telemetry is missing or irregular.
            const channelTotalsPromise = Promise.all([0, 1].map(async (channel) => {
                const counterQuery = () => {
                    let query = supabase
                        .from('energy_readings')
                        .select('device_id, energy_total_wh, created_at')
                        .eq('channel', channel)
                        .not('energy_total_wh', 'is', null)

                    if (PUBLIC_METER_DEVICE_ID && PUBLIC_TELEMETRY_SITE_ID) {
                        query = query.eq('device_id', PUBLIC_METER_DEVICE_ID)
                        query = query.or(siteOrLegacyFilter(PUBLIC_TELEMETRY_SITE_ID))
                    }
                    return query
                }

                const [beforeStartRes, afterStartRes, beforeEndRes, afterEndRes] = await Promise.all([
                    counterQuery()
                        .lte('created_at', startIso)
                        .order('created_at', { ascending: false })
                        .limit(1),
                    counterQuery()
                        .gte('created_at', startIso)
                        .lte('created_at', endIso)
                        .order('created_at', { ascending: true })
                        .limit(1),
                    counterQuery()
                        .gte('created_at', startIso)
                        .lte('created_at', endIso)
                        .order('created_at', { ascending: false })
                        .limit(1),
                    counterQuery()
                        .gte('created_at', endIso)
                        .order('created_at', { ascending: true })
                        .limit(1),
                ])

                if (beforeStartRes.error || afterStartRes.error || beforeEndRes.error || afterEndRes.error) {
                    return { channel, totalKWh: null }
                }

                const startCounter = interpolateCounterAt(
                    beforeStartRes.data?.[0] as CounterReading | undefined,
                    afterStartRes.data?.[0] as CounterReading | undefined,
                    startDate.getTime(),
                )
                const interpolatedEndCounter = interpolateCounterAt(
                    beforeEndRes.data?.[0] as CounterReading | undefined,
                    afterEndRes.data?.[0] as CounterReading | undefined,
                    endDate.getTime(),
                )
                const lastInRange = asCounterPoint(beforeEndRes.data?.[0] as CounterReading | undefined)
                const isCurrentOrFutureRange = endDate.getTime() >= Date.now()
                const endCounter = interpolatedEndCounter ?? (isCurrentOrFutureRange ? lastInRange : null)

                const isValidDelta = startCounter !== null
                    && endCounter !== null
                    && startCounter.deviceId === endCounter.deviceId
                    && endCounter.timestampMs > startCounter.timestampMs
                    && endCounter.wattHours >= startCounter.wattHours

                return {
                    channel,
                    totalKWh: isValidDelta ? (endCounter.wattHours - startCounter.wattHours) / 1000 : null,
                }
            }))

            try {
                const [rData, readingsData, schedData, totalsData] = await Promise.all([ratesPromise, readingsPromise, schedulePromise, channelTotalsPromise])
                if (cancelled) return

                if (rData.results) {
                    rates = rData.results
                    if (rates.length === 0 && viewMode === "tomorrow") {
                        setHasRates(false)
                    } else {
                        setHasRates(true)
                    }
                }

                readings = readingsData
                setTelemetryState(readingsFetchFailed ? "error" : readings.length > 0 ? "ok" : "empty")

                if (schedData.data) {
                    scheduleSlots = schedData.data
                } else if (schedData.error) {
                    console.error("Schedule fetch error:", schedData.error)
                }

                channelTotals = new Map<number, number | null>(totalsData.map((result) => [result.channel, result.totalKWh]))
            } catch (e) {
                if (cancelled) return
                console.error("Fetch error", e)
                setHasRates(false)
                setTelemetryState("error")
            }

            // Track last update time from most recent reading
            if (readings.length > 0) {
                const latestReading = readings.reduce((latest, current) => {
                    const currentTime = new Date(current.bucket_time)
                    const latestTime = new Date(latest.bucket_time)
                    return currentTime > latestTime ? current : latest
                })
                setLastUpdate(new Date(latestReading.bucket_time))
            } else {
                setLastUpdate(null)
            }

            // --- Calculate Totals (kWh) ---
            setTotals({
                peak: channelTotals.get(0) ?? null,
                offPeak: channelTotals.get(1) ?? null,
            })
            // -----------------------------

            // 3. Build Unified Buckets (Dynamic Granularity)

            const buckets: ChartPoint[] = []
            const currentCursor = new Date(startDate)

            // Map for quick lookup
            const readingsBySlot = new Map<number, DownsampledReading[]>()
            readings.forEach(r => {
                // Always using RPC now, so always use bucket_time
                const t = new Date(r.bucket_time)

                // Align to bucket using UTC methods to avoid local timezone offset
                const remainder = t.getUTCMinutes() % bucketMinutes
                t.setUTCMinutes(t.getUTCMinutes() - remainder, 0, 0)

                const key = t.getTime()
                if (!readingsBySlot.has(key)) readingsBySlot.set(key, [])
                readingsBySlot.get(key)?.push(r)
            })

            rates.sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())

            while (currentCursor <= endDate) {
                const slotTime = currentCursor.getTime()

                // Find Rate
                const rateObj = rates.find(r => {
                    const from = new Date(r.valid_from).getTime()
                    const to = new Date(r.valid_to).getTime()
                    return slotTime >= from && slotTime < to
                })

                // A long-view bucket can contain a schedule beginning at :30,
                // so use interval overlap instead of testing only its start.
                const bucketEndTime = slotTime + (bucketMinutes * 60 * 1000)
                const isScheduled = scheduleSlots.some((slot) => {
                    const scheduledStart = Date.parse(slot.slot_start)
                    const scheduledEnd = Date.parse(slot.slot_end)
                    return scheduledStart < bucketEndTime && scheduledEnd > slotTime
                })

                const slotReadings = readingsBySlot.get(slotTime) || []

                // Missing telemetry is unknown, not a measured 0W sample.
                const r0 = slotReadings.find(r => r.channel === 0)
                const r1 = slotReadings.find(r => r.channel === 1)
                const power0 = r0?.avg_power == null ? null : Number(r0.avg_power)
                const power1 = r1?.avg_power == null ? null : Number(r1.avg_power)
                const avg0 = power0 !== null && Number.isFinite(power0) ? power0 : null
                const avg1 = power1 !== null && Number.isFinite(power1) ? power1 : null

                buckets.push({
                    raw_time: slotTime,
                    rate: rateObj ? rateObj.value_inc_vat : null,
                    isScheduled: isScheduled,
                    power_0: avg0,
                    power_1: avg1
                })

                currentCursor.setUTCMinutes(currentCursor.getUTCMinutes() + bucketMinutes)
            }

            // Healthy one-minute polling can skip one bucket because network
            // time is added after each 60-second sleep. Bridge only one enclosed
            // missing minute; longer or edge gaps remain visibly unknown.
            if (bucketMinutes === 1) {
                const peakTrace = bridgeSingleBucketGaps(buckets.map((point) => point.power_0))
                const storageTrace = bridgeSingleBucketGaps(buckets.map((point) => point.power_1))
                buckets.forEach((point, index) => {
                    point.power_0 = peakTrace[index]
                    point.power_1 = storageTrace[index]
                })
            }

            setData(buckets)
        }

        void fetchData()
        return () => {
            cancelled = true
        }
    }, [viewMode, customDate, refreshKey, ukToday, ukYesterday])

    const isDayView = viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom"
    const chartBucketMinutes = isDayView ? 1 : 60
    const chartBucketMs = chartBucketMinutes * 60_000
    const scheduledPeriods = chartBucketMinutes === 1
        ? collectScheduledPeriods(data, chartBucketMinutes)
        : []

    // Check for missing Tomorrow data
    // We check hasRates because 'data' might be populated with empty buckets
    if (viewMode === "tomorrow" && !hasRates) {
        return (
            <Card className="col-span-4">
                <CardHeader>
                    <CardTitle>Usage & Price History</CardTitle>
                </CardHeader>
                <CardContent className="h-[400px] flex items-center justify-center">
                    <div className="text-center space-y-4">
                        <Button variant="outline" size="sm" onClick={() => navigateToDateView("today")}>
                            Back to Today
                        </Button>
                        <p className="text-muted-foreground">
                            Tomorrow&apos;s rates are not yet available from Octopus Energy. <br />
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
        const seconds = Math.max(0, Math.floor((nowMs - date.getTime()) / 1000))
        if (seconds < 60) return `${seconds}s ago`
        const minutes = Math.floor(seconds / 60)
        if (minutes < 60) return `${minutes}m ago`
        const hours = Math.floor(minutes / 60)
        if (hours < 24) return `${hours}h ago`
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    // One-minute fixed-cadence telemetry should stay fresh through a few
    // transient cloud delays, but a stopped collector must become visible.
    const systemStatus = lastUpdate && (nowMs - lastUpdate.getTime()) < 5 * 60 * 1000 ? "active" : "stale"

    // Find current time position for vertical highlight
    const now = new Date(nowMs)
    let currentTimestamp: number | null = null

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
        const maxDiff = (viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom") ? 60000 : 3600000
        if (minDiff < maxDiff) {
            currentTimestamp = closestPoint.raw_time
        }
    }

    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-col space-y-4 sm:flex-row sm:items-center sm:justify-between sm:space-y-0 pb-2">
                <div className="space-y-1">
                    <div className="flex items-center gap-3">
                        <CardTitle className="font-display text-xl sm:text-2xl font-extrabold">Usage & Price History</CardTitle>
                        {lastUpdate && (
                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${systemStatus === "active"
                                ? "bg-live/10 text-live border border-live/20"
                                : "bg-orange-500/10 text-orange-600 border border-orange-500/20"
                                }`}>
                                <div className={`w-1.5 h-1.5 rounded-full ${systemStatus === "active" ? "bg-live" : "bg-orange-500"
                                    } animate-pulse`} />
                                <span>Updated {formatTimeAgo(lastUpdate)}</span>
                            </div>
                        )}
                        {!lastUpdate && telemetryState !== "loading" && (
                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${telemetryState === "error"
                                ? "bg-red-500/10 text-red-600 border-red-500/20"
                                : "bg-amber-500/10 text-amber-600 border-amber-500/20"
                                }`}>
                                <div className={`w-1.5 h-1.5 rounded-full ${telemetryState === "error" ? "bg-red-500" : "bg-amber-500"}`} />
                                <span>{telemetryState === "error" ? "Telemetry unavailable" : "No telemetry in range"}</span>
                            </div>
                        )}
                    </div>
                    <CardDescription className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0">
                        <span>Total heater usage in selected range:</span>
                        <span className="hidden sm:inline text-muted-foreground mx-2">|</span>
                        <div className="flex gap-4 sm:gap-0">
                            <span className="text-teal font-bold whitespace-nowrap">
                                Boost: {totals.peak === null ? "—" : `${totals.peak.toFixed(2)} kWh`}
                            </span>
                            <span className="hidden sm:inline text-muted-foreground mx-2">|</span>
                            <span className="text-teal-glow font-bold whitespace-nowrap">
                                Storage: {totals.offPeak === null ? "—" : `${totals.offPeak.toFixed(2)} kWh`}
                            </span>
                        </div>
                    </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2 items-center">
                    <Button variant={viewMode === "today" ? "default" : "outline"} size="sm" onClick={() => {
                        navigateToDateView("today")
                    }}>Today</Button>
                    <Button variant={viewMode === "tomorrow" ? "default" : "outline"} size="sm" onClick={() => {
                        navigateToDateView("tomorrow")
                    }}>Tomorrow</Button>
                    <Button variant={viewMode === "7d" ? "default" : "outline"} size="sm" onClick={() => {
                        navigateToDateView("7d")
                    }}>7d</Button>
                    <Button variant={viewMode === "30d" ? "default" : "outline"} size="sm" onClick={() => {
                        navigateToDateView("30d")
                    }}>30d</Button>
                    <input
                        type="date"
                        min={EARLIEST_DASHBOARD_DATE}
                        max={ukTomorrow}
                        value={calendarValueForView(viewMode, ukToday, ukTomorrow, customDate)}
                        aria-label="Choose a date"
                        title={viewMode === "today" ? "Today" : viewMode === "tomorrow" ? "Tomorrow" : viewMode === "custom" ? "Selected historical date" : "Choose a date"}
                        onChange={(e) => {
                            if (!isValidCalendarDate(e.target.value)) return

                            const selection = classifyDateSelection(e.target.value, ukToday, ukTomorrow)
                            if (selection.customDate) {
                                navigateToDateView("custom", selection.customDate)
                                return
                            }

                            navigateToDateView(selection.viewMode)
                        }}
                        className={`h-9 rounded-md border px-2 text-sm cursor-pointer
                            ${viewMode === "custom"
                                ? "bg-primary text-primary-foreground border-primary"
                                : "bg-background border-input text-foreground hover:bg-accent hover:text-accent-foreground"
                            }`
                        }
                    />
                </div>
            </CardHeader>
            <CardContent className="pl-2">
                <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 px-2 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                        <span className="h-3 w-5 rounded-sm border border-teal/30 bg-teal/10" />
                        Scheduled storage-heater ON window
                    </span>
                    <span>Filled traces show measured power draw; the rate line is the live Octopus Agile price</span>
                </div>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />

                            {/* Show controller intent independently from measured power draw. */}
                            {scheduledPeriods.map((period, idx) => (
                                <ReferenceArea
                                    key={`scheduled-${idx}`}
                                    x1={period.start}
                                    x2={period.end}
                                    yAxisId="left"
                                    fill="var(--teal)"
                                    fillOpacity={0.08}
                                    stroke="var(--teal)"
                                    strokeOpacity={0.22}
                                />
                            ))}

                            {/* Current time indicator - only show for today and 7d/30d views */}
                            {currentTimestamp && viewMode === "today" && (
                                <ReferenceLine
                                    x={currentTimestamp}
                                    yAxisId="left"
                                    stroke="var(--cold)"
                                    strokeWidth={2}
                                    strokeDasharray="4 2"
                                    label={{
                                        value: "NOW",
                                        position: "top",
                                        fill: "var(--cold)",
                                        fontSize: 11,
                                        fontWeight: 700
                                    }}
                                />
                            )}

                            <XAxis
                                dataKey="raw_time"
                                type="number"
                                domain={([dataMin, dataMax]) => [dataMin, dataMax + chartBucketMs]}
                                scale="time"
                                stroke="var(--muted-foreground)"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => new Date(Number(value)).toLocaleString([], {
                                    timeZone: 'Europe/London',
                                    month: isDayView ? undefined : 'numeric',
                                    day: isDayView ? undefined : 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                })}
                                minTickGap={(viewMode === "today" || viewMode === "tomorrow" || viewMode === "custom") ? 30 : 60}
                            />
                            {/* Left Axis: Price. Rust is the single signal accent, reserved for
                                the Octopus Agile rate everywhere it appears. */}
                            <YAxis
                                yAxisId="left"
                                stroke="var(--rust)"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                domain={[0, 'dataMax + 5']}
                                tickFormatter={(value) => `${value}p`}
                                label={{ value: 'Agile Rate (p/kWh)', angle: -90, position: 'insideLeft', fill: 'var(--rust)' }}
                            />
                            {/* Right Axis: Power — teal carries data, per brand spec. */}
                            <YAxis
                                yAxisId="right"
                                orientation="right"
                                stroke="var(--teal)"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}W`}
                                label={{ value: 'Power (W)', angle: 90, position: 'insideRight', fill: 'var(--teal)' }}
                            />

                            <Tooltip
                                contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", color: "var(--card-foreground)" }}
                                labelFormatter={(value) => new Date(Number(value)).toLocaleString([], {
                                    timeZone: 'Europe/London',
                                    month: isDayView ? undefined : 'numeric',
                                    day: isDayView ? undefined : 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    timeZoneName: isDayView ? 'short' : undefined,
                                })}
                                formatter={(value, name, props) => {
                                    if (name === "Rate (p/kWh)") {
                                        const point = props.payload as ChartPoint | undefined
                                        return [
                                            <div key="rate">
                                                <span>{Number(value).toFixed(2)}p</span>
                                                {point?.isScheduled && <span className="ml-2 text-teal font-bold">● Scheduled</span>}
                                            </div>,
                                            name
                                        ]
                                    }
                                    return [`${Number(value).toFixed(0)}W`, name]
                                }}
                            />
                            <Legend />

                            {/* Rate Line (Left Axis) — rust is the Octopus Agile rate signal, kept
                                consistent with the live-rate figure above the chart. */}
                            <Line
                                yAxisId="left"
                                type="stepAfter"
                                dataKey="rate"
                                name="Rate (p/kWh)"
                                stroke="var(--rust)"
                                strokeWidth={2}
                                dot={false}
                                connectNulls
                            />

                            {/* Filled step traces make real heater cycling readable. Both heaters
                                are the same telemetry "data" stream per brand spec, so they share
                                the teal family and differ only by shade. */}
                            <Area
                                yAxisId="right"
                                type="stepAfter"
                                dataKey="power_0"
                                name="Boost Heater (W)"
                                stroke="var(--teal)"
                                strokeWidth={2}
                                fill="var(--teal)"
                                fillOpacity={0.14}
                                baseValue={0}
                                dot={false}
                            />
                            <Area
                                yAxisId="right"
                                type="stepAfter"
                                dataKey="power_1"
                                name="Storage Heater (W)"
                                stroke="var(--teal-glow)"
                                strokeWidth={2}
                                fill="var(--teal-glow)"
                                fillOpacity={0.22}
                                baseValue={0}
                                dot={false}
                            />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    )
}

