import { NextResponse } from "next/server"
import { createClient, type SupabaseClient } from "@supabase/supabase-js"
import { getUKDateBoundaries } from "@/lib/date-utils"

const PRODUCT = "AGILE-24-10-01"
const REGION = "C"
const TARIFF = `E-1R-${PRODUCT}-${REGION}`
const OCTOPUS_BASE = `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/`

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
    channel: number
    created_at: string
    energy_total_wh: number
}

interface WindowResult {
    avg_paid_ppkwh: number | null
    total_kwh_priced: number
    total_kwh_measured: number
    total_cost_gbp: number
    coverage_ratio: number
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
    endIso: string
): Promise<EnergyReading[]> {
    const previousResponse = await supabase
        .from("energy_readings")
        .select("channel, created_at, energy_total_wh")
        .eq("channel", channel)
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
        const pageResponse = await supabase
            .from("energy_readings")
            .select("channel, created_at, energy_total_wh")
            .eq("channel", channel)
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

export async function GET() {
    try {
        const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
        const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

        if (!supabaseUrl || !supabaseAnonKey) {
            return NextResponse.json({ error: "Supabase environment variables are missing" }, { status: 500 })
        }

        const supabase = createClient(supabaseUrl, supabaseAnonKey)

        const yesterdayBounds = getUKDateBoundaries(-1)
        const sevenDayStart = getUKDateBoundaries(-7).start
        const thirtyDayStart = getUKDateBoundaries(-30).start

        const globalStart = thirtyDayStart
        const globalEnd = yesterdayBounds.end

        const [rates, channel0Readings, channel1Readings] = await Promise.all([
            fetchRates(globalStart.toISOString(), globalEnd.toISOString()),
            fetchReadingsForChannel(supabase, 0, globalStart.toISOString(), globalEnd.toISOString()),
            fetchReadingsForChannel(supabase, 1, globalStart.toISOString(), globalEnd.toISOString()),
        ])

        const readingsByChannel = [channel0Readings, channel1Readings]

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

        return NextResponse.json({
            scope: "all_heaters_combined",
            method: "kwh_weighted_avg_price_paid",
            windows: "uk_calendar_complete_days",
            yesterday,
            last7d,
            last30d,
            generated_at: new Date().toISOString(),
        })
    } catch {
        return NextResponse.json({ error: "Failed to compute energy stats" }, { status: 502 })
    }
}