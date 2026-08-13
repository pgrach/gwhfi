import { NextResponse } from "next/server"
import { createClient, type SupabaseClient } from "@supabase/supabase-js"
import { getUKDateBoundaries, getUKDateBoundariesForDate, getUKDateString } from "@/lib/date-utils"
import { isHistoricalCalendarDate } from "@/lib/date-selection"
import { OCTOPUS_RATES_URL } from "@/lib/octopus-config"
import {
    buildEnergyCounterSeriesRequest,
    resolveMeterDeviceId,
    siteOrLegacyFilter,
} from "@/lib/telemetry-scope"
import { fetchCompleteDownsampledRange } from "@/lib/downsampled-readings"
import { planAnalyticsRanges } from "@/lib/analytics-ranges"

const OCTOPUS_BASE = OCTOPUS_RATES_URL
// Five-minute counter buckets keep a 30-day response compact while limiting
// tariff-boundary allocation uncertainty for short thermostat cycles.
const COUNTER_SERIES_BUCKET_SECONDS = 5 * 60

interface RateApiResult {
    value_inc_vat: number
    valid_from: string
    valid_to: string
}

interface RateInterval {
    valueIncVat: number
    fromMs: number
    toMs: number
}

interface EnergyReading {
    device_id: string
    channel: number
    created_at: string
    energy_total_wh: number | null
}

interface EnergyCounterSeriesReading extends EnergyReading {
    bucket_time: string
}

interface WindowResult {
    avg_paid_ppkwh: number | null
    total_kwh_priced: number
    total_kwh_measured: number
    total_cost_gbp: number
    coverage_ratio: number
}

interface SelectedDayResult {
    date: string
    window: WindowResult
}

interface OctopusResponse {
    next: string | null
    results: RateApiResult[]
}

function round(value: number, digits: number): number {
    return Number(value.toFixed(digits))
}

function overlaps(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
    return aStart < bEnd && aEnd > bStart
}

async function fetchRates(startIso: string, endIso: string): Promise<RateInterval[]> {
    let nextUrl = `${OCTOPUS_BASE}?period_from=${encodeURIComponent(startIso)}&period_to=${encodeURIComponent(endIso)}&page_size=1500`
    const intervals: RateInterval[] = []

    while (nextUrl) {
        const response = await fetch(nextUrl, { next: { revalidate: 300 } })
        if (!response.ok) {
            throw new Error("Failed to fetch Octopus rates")
        }

        const data: OctopusResponse = await response.json()
        for (const item of data.results ?? []) {
            const fromMs = new Date(item.valid_from).getTime()
            const toMs = new Date(item.valid_to).getTime()
            if (Number.isFinite(fromMs) && Number.isFinite(toMs) && toMs > fromMs) {
                intervals.push({
                    valueIncVat: item.value_inc_vat,
                    fromMs,
                    toMs,
                })
            }
        }

        nextUrl = data.next ?? ""
    }

    return intervals.sort((a, b) => a.fromMs - b.fromMs)
}

async function fetchReadingsForChannel(
    supabase: SupabaseClient,
    channel: number,
    startIso: string,
    endIso: string,
    meterDeviceId: string | null,
    siteId: string | null,
): Promise<EnergyReading[]> {
    let previousQuery = supabase
        .from("energy_readings")
        .select("device_id, channel, created_at, energy_total_wh")
        .eq("channel", channel)

    if (meterDeviceId && siteId) {
        previousQuery = previousQuery.eq("device_id", meterDeviceId)
        previousQuery = previousQuery.or(siteOrLegacyFilter(siteId))
    }

    const previousResponse = await previousQuery
        .lt("created_at", startIso)
        .order("created_at", { ascending: false })
        .limit(1)

    if (previousResponse.error) {
        throw new Error(`Failed to fetch previous energy reading for channel ${channel}`)
    }

    const pageSize = 1000
    let from = 0
    const readings: EnergyReading[] = []

    while (true) {
        let pageQuery = supabase
            .from("energy_readings")
            .select("device_id, channel, created_at, energy_total_wh")
            .eq("channel", channel)

        if (meterDeviceId && siteId) {
            pageQuery = pageQuery.eq("device_id", meterDeviceId)
            pageQuery = pageQuery.or(siteOrLegacyFilter(siteId))
        }

        const pageResponse = await pageQuery
            .gte("created_at", startIso)
            .lte("created_at", endIso)
            .order("created_at", { ascending: true })
            .range(from, from + pageSize - 1)

        if (pageResponse.error) {
            throw new Error(`Failed to fetch energy readings for channel ${channel}`)
        }

        const page = (pageResponse.data ?? []) as EnergyReading[]
        if (page.length === 0) {
            break
        }

        readings.push(...page)

        if (page.length < pageSize) {
            break
        }

        from += pageSize
    }

    const previous = (previousResponse.data ?? []) as EnergyReading[]
    return [...previous.reverse(), ...readings]
}

interface AnalyticsRangeData {
    rates: RateInterval[]
    readingsByChannel: EnergyReading[][]
}

async function fetchScopedCounterReadings(
    supabase: SupabaseClient,
    startMs: number,
    endMs: number,
    meterDeviceId: string,
    siteId: string,
): Promise<EnergyReading[][]> {
    const channels = [0, 1] as const
    const startIso = new Date(startMs).toISOString()

    const previousResponsesPromise = Promise.all(channels.map((channel) => (
        supabase
            .from("energy_readings")
            .select("device_id, channel, created_at, energy_total_wh")
            .eq("device_id", meterDeviceId)
            .or(siteOrLegacyFilter(siteId))
            .eq("channel", channel)
            .not("energy_total_wh", "is", null)
            .lt("created_at", startIso)
            .order("created_at", { ascending: false })
            .limit(1)
    )))

    // UK date helpers expose inclusive end-of-day instants. The counter RPC is
    // half-open, so add 1ms to preserve the existing window coverage exactly.
    const seriesResultPromise = fetchCompleteDownsampledRange<EnergyCounterSeriesReading>(
        startMs,
        endMs + 1,
        COUNTER_SERIES_BUCKET_SECONDS,
        async (chunkStartIso, chunkEndIso) => {
            const request = buildEnergyCounterSeriesRequest(
                chunkStartIso,
                chunkEndIso,
                COUNTER_SERIES_BUCKET_SECONDS,
                siteId,
                meterDeviceId,
            )
            const response = await supabase.rpc(request.functionName, request.params)
            return {
                data: response.data as EnergyCounterSeriesReading[] | null,
                error: response.error,
            }
        },
    )

    const [previousResponses, seriesResult] = await Promise.all([
        previousResponsesPromise,
        seriesResultPromise,
    ])

    if (previousResponses.some((response) => response.error)) {
        throw new Error("Failed to fetch counter reading before analytics range")
    }
    if (seriesResult.errors.length > 0) {
        throw new Error("Failed to fetch compact energy counter series")
    }

    return channels.map((channel, index) => {
        const previous = (previousResponses[index].data ?? []) as EnergyReading[]
        const series = seriesResult.data.filter((reading) => reading.channel === channel)
        return [...previous, ...series]
    })
}

async function fetchAnalyticsRange(
    supabase: SupabaseClient,
    startMs: number,
    endMs: number,
    meterDeviceId: string | null,
    siteId: string | null,
): Promise<AnalyticsRangeData> {
    const startIso = new Date(startMs).toISOString()
    const endIso = new Date(endMs).toISOString()
    const readingsPromise = meterDeviceId && siteId
        ? fetchScopedCounterReadings(
            supabase,
            startMs,
            endMs,
            meterDeviceId,
            siteId,
        )
        : Promise.all([
            fetchReadingsForChannel(supabase, 0, startIso, endIso, null, null),
            fetchReadingsForChannel(supabase, 1, startIso, endIso, null, null),
        ])

    const [rates, readingsByChannel] = await Promise.all([
        fetchRates(startIso, endIso),
        readingsPromise,
    ])
    return { rates, readingsByChannel }
}

function computeWindowResult(
    rates: RateInterval[],
    readingsByChannel: EnergyReading[][],
    startMs: number,
    endMs: number
): WindowResult {
    let totalCostPence = 0
    let totalKwhPriced = 0
    let totalKwhMeasured = 0

    const windowRates = rates.filter((rate) => overlaps(rate.fromMs, rate.toMs, startMs, endMs))

    for (const readings of readingsByChannel) {
        for (let index = 1; index < readings.length; index++) {
            const previous = readings[index - 1]
            const current = readings[index]

            // Never interpret a counter jump between two physical meters as
            // consumption, including during the legacy unscoped rollout mode.
            if (previous.device_id !== current.device_id) {
                continue
            }

            const previousMs = new Date(previous.created_at).getTime()
            const currentMs = new Date(current.created_at).getTime()
            if (!Number.isFinite(previousMs) || !Number.isFinite(currentMs) || currentMs <= previousMs) {
                continue
            }

            const segmentStart = Math.max(previousMs, startMs)
            const segmentEnd = Math.min(currentMs, endMs)
            if (segmentEnd <= segmentStart) {
                continue
            }

            if (current.energy_total_wh === null || previous.energy_total_wh === null) {
                continue
            }

            const deltaWh = current.energy_total_wh - previous.energy_total_wh
            if (!Number.isFinite(deltaWh) || deltaWh <= 0) {
                continue
            }

            const fullSegmentDurationMs = currentMs - previousMs
            const clippedDurationMs = segmentEnd - segmentStart
            const clippedDeltaKwh = (deltaWh / 1000) * (clippedDurationMs / fullSegmentDurationMs)

            if (!Number.isFinite(clippedDeltaKwh) || clippedDeltaKwh <= 0) {
                continue
            }

            totalKwhMeasured += clippedDeltaKwh

            for (const rate of windowRates) {
                const overlapStart = Math.max(segmentStart, rate.fromMs)
                const overlapEnd = Math.min(segmentEnd, rate.toMs)
                if (overlapEnd <= overlapStart) {
                    continue
                }

                const overlapRatio = (overlapEnd - overlapStart) / clippedDurationMs
                const overlapKwh = clippedDeltaKwh * overlapRatio
                totalKwhPriced += overlapKwh
                totalCostPence += overlapKwh * rate.valueIncVat
            }
        }
    }

    const avgPaid = totalKwhPriced > 0 ? totalCostPence / totalKwhPriced : null
    const coverage = totalKwhMeasured > 0 ? totalKwhPriced / totalKwhMeasured : 0

    return {
        avg_paid_ppkwh: avgPaid === null ? null : round(avgPaid, 3),
        total_kwh_priced: round(totalKwhPriced, 3),
        total_kwh_measured: round(totalKwhMeasured, 3),
        total_cost_gbp: round(totalCostPence / 100, 2),
        coverage_ratio: round(coverage, 4),
    }
}

export async function GET(request: Request) {
    try {
        const yesterdayDate = getUKDateString(-1)
        const selectedDateRaw = new URL(request.url).searchParams.get("selectedDate")
        const selectedDate = isHistoricalCalendarDate(selectedDateRaw, yesterdayDate)
            ? selectedDateRaw
            : null

        const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
        const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
        const meterDeviceId = resolveMeterDeviceId(
            process.env.SHELLY_METER_DEVICE_ID,
            process.env.NEXT_PUBLIC_SHELLY_METER_DEVICE_ID,
        )
        const siteId = resolveMeterDeviceId(
            process.env.TELEMETRY_SITE_ID,
            process.env.NEXT_PUBLIC_TELEMETRY_SITE_ID,
        )

        if (!supabaseUrl || !supabaseAnonKey) {
            return NextResponse.json({ error: "Supabase environment variables are missing" }, { status: 500 })
        }

        const supabase = createClient(supabaseUrl, supabaseAnonKey)

        const yesterdayBounds = getUKDateBoundaries(-1)
        const sevenDayStart = getUKDateBoundaries(-7).start
        const thirtyDayStart = getUKDateBoundaries(-30).start

        const selectedDateBounds = selectedDate
            ? getUKDateBoundariesForDate(selectedDate)
            : null

        const globalEnd = yesterdayBounds.end
        const rangePlan = planAnalyticsRanges(
            {
                startMs: thirtyDayStart.getTime(),
                endMs: globalEnd.getTime(),
            },
            selectedDateBounds
                ? {
                    startMs: selectedDateBounds.start.getTime(),
                    endMs: selectedDateBounds.end.getTime(),
                }
                : null,
        )

        // Keep one bounded recent-range query regardless of how old the user-
        // selected date is. If that day lies outside the recent window, fetch
        // only that isolated day afterwards so concurrent RPCs remain capped.
        const recentData = await fetchAnalyticsRange(
            supabase,
            rangePlan.recent.startMs,
            rangePlan.recent.endMs,
            meterDeviceId,
            siteId,
        )
        const selectedSeparateData = rangePlan.selectedSeparate
            ? await fetchAnalyticsRange(
                supabase,
                rangePlan.selectedSeparate.startMs,
                rangePlan.selectedSeparate.endMs,
                meterDeviceId,
                siteId,
            )
            : null

        const rates = recentData.rates
        const readingsByChannel = recentData.readingsByChannel

        const yesterday = computeWindowResult(
            rates,
            readingsByChannel,
            yesterdayBounds.start.getTime(),
            yesterdayBounds.end.getTime()
        )
        const last7d = computeWindowResult(
            rates,
            readingsByChannel,
            sevenDayStart.getTime(),
            yesterdayBounds.end.getTime()
        )
        const last30d = computeWindowResult(
            rates,
            readingsByChannel,
            thirtyDayStart.getTime(),
            yesterdayBounds.end.getTime()
        )

        const selectedData = selectedSeparateData ?? recentData
        const selected_day: SelectedDayResult | null = selectedDateBounds && selectedDate
            ? {
                date: selectedDate,
                window: computeWindowResult(
                    selectedData.rates,
                    selectedData.readingsByChannel,
                    selectedDateBounds.start.getTime(),
                    selectedDateBounds.end.getTime()
                ),
            }
            : null

        return NextResponse.json({
            scope: "all_heaters_combined",
            telemetry_scope: meterDeviceId && siteId
                ? "configured_site_and_meter"
                : meterDeviceId || siteId
                    ? "partially_configured_legacy"
                    : "all_sites_and_devices_legacy",
            method: "kwh_weighted_avg_price_paid",
            counter_series: meterDeviceId && siteId
                ? `latest_real_counter_per_${COUNTER_SERIES_BUCKET_SECONDS}_seconds`
                : "raw_rows_legacy",
            windows: "uk_calendar_complete_days",
            yesterday,
            last7d,
            last30d,
            selected_day,
            generated_at: new Date().toISOString(),
        })
    } catch {
        return NextResponse.json({ error: "Failed to compute energy stats" }, { status: 502 })
    }
}
