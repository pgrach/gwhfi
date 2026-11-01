import baselineArtifact from "../data/orbis-baseline-v1.json"

const UK_TIME_ZONE = "Europe/London"
const HALF_HOUR_MS = 30 * 60 * 1_000
const PROFILE_WEIGHT_TOLERANCE = 1e-6

export type OrbisProfileName = "weekday" | "weekend"

export interface AgileTariffInterval {
    valid_from: string
    valid_to: string
    /** Pence per kWh, inclusive of VAT. Negative Agile prices are valid. */
    value_inc_vat: number
}

interface OrbisBaselineProfile {
    sample_days: number
    weights: Record<string, number>
}

export interface OrbisBaselineArtifact {
    version: string
    device_id: string
    channel: number
    baseline_start: string
    baseline_end: string
    excluded_local_window: string
    profiles: {
        all: OrbisBaselineProfile
        weekday: OrbisBaselineProfile
        weekend: OrbisBaselineProfile
    }
}

export interface OrbisOnlyCostInput {
    /** UK calendar date in YYYY-MM-DD form. */
    localDate: string
    /** The day's measured energy. The counterfactual changes timing, not energy. */
    actualKwh: number
    /** Complete set of real Octopus half-hour intervals covering the UK day. */
    tariffIntervals: AgileTariffInterval[]
}

export interface OrbisBaselineMetadata {
    artifactVersion: string
    deviceId: string
    channel: number
    baselineStart: string
    baselineEnd: string
    excludedLocalWindow: string
    profile: OrbisProfileName
    sampleDays: number
    timeZone: typeof UK_TIME_ZONE
}

export interface OrbisBaselineArtifactMetadata {
    artifactVersion: string
    deviceId: string
    channel: number
    baselineStart: string
    baselineEnd: string
    excludedLocalWindow: string
    timeZone: typeof UK_TIME_ZONE
    sampleDays: {
        all: number
        weekday: number
        weekend: number
    }
}

export interface OrbisIntervalAllocation {
    validFrom: string
    validTo: string
    localTime: string
    ratePencePerKwh: number
    rawProfileWeight: number
    normalizedWeight: number
    expectedKwh: number
    expectedCostGbp: number
}

export interface OrbisOnlyCostEstimate {
    localDate: string
    actualKwh: number
    expectedOrbisCostGbp: number
    /** Null only when actualKwh is zero and an average rate is undefined. */
    expectedOrbisAveragePencePerKwh: number | null
    profile: OrbisProfileName
    baseline: OrbisBaselineMetadata
    /** 46, 48, or 50 real intervals on a complete UK calendar day. */
    tariffIntervalCount: number
    /** Weight represented before DST renormalization. */
    availableProfileWeight: number
    intervals: OrbisIntervalAllocation[]
}

export type StorageSavingsStatus =
    | "available"
    | "no_usage"
    | "insufficient_data"
    | "not_applicable"

export interface StorageSavingsDayInput {
    /** UK calendar date represented by this complete-day observation. */
    localDate: string
    /** All storage-heater energy measured in the day. */
    measuredKwh: number
    /** Measured energy that could be matched to an Agile interval. */
    pricedKwh: number
    /** Exact (unrounded) cost of pricedKwh under the observed smart timing. */
    actualCostGbp: number
    /** Complete set of real Agile half-hour intervals covering the UK day. */
    tariffIntervals: AgileTariffInterval[]
}

export interface StorageSavingsEvaluationInput {
    days: StorageSavingsDayInput[]
    smartControlStartDate: string
    minimumCoverageRatio: number
}

export interface StorageSavingsEvaluation {
    status: StorageSavingsStatus
    actualAveragePencePerKwh: number | null
    actualCostGbp: number
    withoutAlgorithmAveragePencePerKwh: number | null
    withoutAlgorithmCostGbp: number | null
    savedGbp: number | null
    savedPercent: number | null
    measuredKwh: number
    pricedKwh: number
    coverageRatio: number
}

export type HeaterSavingsErrorCode =
    | "invalid_date"
    | "invalid_actual_kwh"
    | "invalid_tariff_interval"
    | "duplicate_tariff_interval"
    | "incomplete_tariff_coverage"
    | "invalid_baseline"

export class HeaterSavingsError extends Error {
    readonly code: HeaterSavingsErrorCode
    readonly details?: Readonly<Record<string, unknown>>

    constructor(
        code: HeaterSavingsErrorCode,
        message: string,
        details?: Readonly<Record<string, unknown>>,
    ) {
        super(message)
        this.name = "HeaterSavingsError"
        this.code = code
        this.details = details
    }
}

export const ORBIS_BASELINE = baselineArtifact as OrbisBaselineArtifact

/** Metadata is available even when a day has no usable energy or tariff data. */
export const ORBIS_BASELINE_METADATA: Readonly<OrbisBaselineArtifactMetadata> = {
    artifactVersion: ORBIS_BASELINE.version,
    deviceId: ORBIS_BASELINE.device_id,
    channel: ORBIS_BASELINE.channel,
    baselineStart: ORBIS_BASELINE.baseline_start,
    baselineEnd: ORBIS_BASELINE.baseline_end,
    excludedLocalWindow: ORBIS_BASELINE.excluded_local_window,
    timeZone: UK_TIME_ZONE,
    sampleDays: {
        all: ORBIS_BASELINE.profiles.all.sample_days,
        weekday: ORBIS_BASELINE.profiles.weekday.sample_days,
        weekend: ORBIS_BASELINE.profiles.weekend.sample_days,
    },
}

const ukDateTimeFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: UK_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
})

interface LocalDateTime {
    date: string
    time: string
}

function localDateTime(timestampMs: number): LocalDateTime {
    const parts = ukDateTimeFormatter.formatToParts(new Date(timestampMs))
    const values: Record<string, string> = {}
    for (const part of parts) {
        if (part.type !== "literal") values[part.type] = part.value
    }

    return {
        date: `${values.year}-${values.month}-${values.day}`,
        time: `${values.hour}:${values.minute}`,
    }
}

function parseCalendarDate(value: string): { year: number; month: number; day: number } {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        throw new HeaterSavingsError("invalid_date", "localDate must be a valid YYYY-MM-DD date")
    }

    const [year, month, day] = value.split("-").map(Number)
    const normalized = new Date(Date.UTC(year, month - 1, day))
    if (
        normalized.getUTCFullYear() !== year
        || normalized.getUTCMonth() !== month - 1
        || normalized.getUTCDate() !== day
    ) {
        throw new HeaterSavingsError("invalid_date", "localDate must be a valid YYYY-MM-DD date")
    }

    return { year, month, day }
}

function profileForDate(
    year: number,
    month: number,
    day: number,
): OrbisProfileName {
    const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
    return weekday === 0 || weekday === 6 ? "weekend" : "weekday"
}

function expectedProfileSlots(): string[] {
    const slots: string[] = []
    for (let hour = 0; hour < 24; hour += 1) {
        if (hour >= 16 && hour < 19) continue
        slots.push(`${String(hour).padStart(2, "0")}:00`)
        slots.push(`${String(hour).padStart(2, "0")}:30`)
    }
    return slots
}

/** Throws if the versioned artifact is internally inconsistent. */
export function validateOrbisBaseline(
    baseline: OrbisBaselineArtifact = ORBIS_BASELINE,
): void {
    const expectedSlots = expectedProfileSlots()

    if (
        !baseline.version
        || !baseline.device_id
        || !Number.isInteger(baseline.channel)
        || baseline.excluded_local_window !== "16:00-19:00"
    ) {
        throw new HeaterSavingsError("invalid_baseline", "Orbis baseline metadata is invalid")
    }

    for (const profileName of ["all", "weekday", "weekend"] as const) {
        const profile = baseline.profiles[profileName]
        if (!profile || !Number.isInteger(profile.sample_days) || profile.sample_days <= 0) {
            throw new HeaterSavingsError(
                "invalid_baseline",
                `Orbis ${profileName} profile has invalid sample_days`,
            )
        }

        const keys = Object.keys(profile.weights).sort()
        if (
            keys.length !== expectedSlots.length
            || expectedSlots.some((slot) => !Object.hasOwn(profile.weights, slot))
        ) {
            throw new HeaterSavingsError(
                "invalid_baseline",
                `Orbis ${profileName} profile must contain every allowed half-hour slot exactly once`,
            )
        }

        let weightSum = 0
        for (const slot of expectedSlots) {
            const weight = profile.weights[slot]
            if (!Number.isFinite(weight) || weight < 0) {
                throw new HeaterSavingsError(
                    "invalid_baseline",
                    `Orbis ${profileName} profile contains an invalid weight at ${slot}`,
                )
            }
            weightSum += weight
        }

        if (Math.abs(weightSum - 1) > PROFILE_WEIGHT_TOLERANCE) {
            throw new HeaterSavingsError(
                "invalid_baseline",
                `Orbis ${profileName} profile weights must sum to one`,
                { weightSum },
            )
        }
    }
}

function expectedUtcStarts(
    localDate: string,
    year: number,
    month: number,
    day: number,
): number[] {
    const nominalUtcMidnight = Date.UTC(year, month - 1, day)
    const starts: number[] = []

    // The UK is always within one hour of UTC. The wider search range makes the
    // day boundary derivation explicit and independent of the host's time zone.
    for (
        let timestampMs = nominalUtcMidnight - (3 * 60 * 60 * 1_000);
        timestampMs < nominalUtcMidnight + (27 * 60 * 60 * 1_000);
        timestampMs += HALF_HOUR_MS
    ) {
        if (localDateTime(timestampMs).date === localDate) starts.push(timestampMs)
    }

    if (![46, 48, 50].includes(starts.length)) {
        throw new HeaterSavingsError(
            "invalid_date",
            "Could not resolve a complete Europe/London calendar day",
            { localDate, intervalCount: starts.length },
        )
    }

    return starts
}

function parseTariffInterval(interval: AgileTariffInterval): {
    fromMs: number
    toMs: number
    rate: number
} {
    const fromMs = Date.parse(interval.valid_from)
    const toMs = Date.parse(interval.valid_to)
    const rate = interval.value_inc_vat

    if (
        !Number.isFinite(fromMs)
        || !Number.isFinite(toMs)
        || toMs <= fromMs
        || !Number.isFinite(rate)
    ) {
        throw new HeaterSavingsError(
            "invalid_tariff_interval",
            "Tariff intervals require valid timestamps and a finite value_inc_vat",
            { interval },
        )
    }

    return { fromMs, toMs, rate }
}

/**
 * Estimate what the measured energy would have cost under the observed
 * Orbis-only timing profile. Energy is held fixed; only its timing changes.
 */
export function estimateOrbisOnlyCost(input: OrbisOnlyCostInput): OrbisOnlyCostEstimate {
    const { year, month, day } = parseCalendarDate(input.localDate)
    if (!Number.isFinite(input.actualKwh) || input.actualKwh < 0) {
        throw new HeaterSavingsError(
            "invalid_actual_kwh",
            "actualKwh must be a finite, non-negative number",
        )
    }
    if (!Array.isArray(input.tariffIntervals)) {
        throw new HeaterSavingsError(
            "invalid_tariff_interval",
            "tariffIntervals must be an array",
        )
    }

    validateOrbisBaseline()

    const profileName = profileForDate(year, month, day)
    const profile = ORBIS_BASELINE.profiles[profileName]
    const expectedStarts = expectedUtcStarts(input.localDate, year, month, day)
    const expectedStartSet = new Set(expectedStarts)
    const ratesByStart = new Map<number, { toMs: number; rate: number }>()

    for (const interval of input.tariffIntervals) {
        const parsed = parseTariffInterval(interval)
        if (!expectedStartSet.has(parsed.fromMs)) continue

        if (parsed.toMs !== parsed.fromMs + HALF_HOUR_MS) {
            throw new HeaterSavingsError(
                "invalid_tariff_interval",
                "Each Agile tariff interval covering the target day must be exactly 30 minutes",
                { validFrom: interval.valid_from, validTo: interval.valid_to },
            )
        }
        if (ratesByStart.has(parsed.fromMs)) {
            throw new HeaterSavingsError(
                "duplicate_tariff_interval",
                "Tariff coverage contains duplicate intervals",
                { validFrom: new Date(parsed.fromMs).toISOString() },
            )
        }
        ratesByStart.set(parsed.fromMs, { toMs: parsed.toMs, rate: parsed.rate })
    }

    const missingStarts = expectedStarts.filter((timestampMs) => !ratesByStart.has(timestampMs))
    if (missingStarts.length > 0) {
        throw new HeaterSavingsError(
            "incomplete_tariff_coverage",
            "Tariff coverage is incomplete for the requested Europe/London day",
            {
                localDate: input.localDate,
                expectedIntervalCount: expectedStarts.length,
                receivedIntervalCount: ratesByStart.size,
                missingValidFrom: missingStarts.map((timestampMs) => new Date(timestampMs).toISOString()),
            },
        )
    }

    const rawAllocations = expectedStarts.map((fromMs) => {
        const tariff = ratesByStart.get(fromMs)
        if (!tariff) {
            // The completeness check above makes this unreachable while keeping
            // the type invariant explicit.
            throw new HeaterSavingsError(
                "incomplete_tariff_coverage",
                "Tariff coverage changed while building the estimate",
            )
        }
        const localTime = localDateTime(fromMs).time
        const rawProfileWeight = profile.weights[localTime] ?? 0
        return { fromMs, localTime, rawProfileWeight, ...tariff }
    })

    const availableProfileWeight = rawAllocations.reduce(
        (sum, interval) => sum + interval.rawProfileWeight,
        0,
    )
    if (!Number.isFinite(availableProfileWeight) || availableProfileWeight <= 0) {
        throw new HeaterSavingsError(
            "invalid_baseline",
            "No Orbis baseline weight is available for the requested day",
        )
    }

    const intervals: OrbisIntervalAllocation[] = rawAllocations.map((interval) => {
        const normalizedWeight = interval.rawProfileWeight / availableProfileWeight
        const expectedKwh = input.actualKwh * normalizedWeight
        return {
            validFrom: new Date(interval.fromMs).toISOString(),
            validTo: new Date(interval.toMs).toISOString(),
            localTime: interval.localTime,
            ratePencePerKwh: interval.rate,
            rawProfileWeight: interval.rawProfileWeight,
            normalizedWeight,
            expectedKwh,
            expectedCostGbp: (expectedKwh * interval.rate) / 100,
        }
    })

    const expectedOrbisCostGbp = intervals.reduce(
        (sum, interval) => sum + interval.expectedCostGbp,
        0,
    )

    return {
        localDate: input.localDate,
        actualKwh: input.actualKwh,
        expectedOrbisCostGbp,
        expectedOrbisAveragePencePerKwh: input.actualKwh === 0
            ? null
            : (expectedOrbisCostGbp * 100) / input.actualKwh,
        profile: profileName,
        baseline: {
            artifactVersion: ORBIS_BASELINE.version,
            deviceId: ORBIS_BASELINE.device_id,
            channel: ORBIS_BASELINE.channel,
            baselineStart: ORBIS_BASELINE.baseline_start,
            baselineEnd: ORBIS_BASELINE.baseline_end,
            excludedLocalWindow: ORBIS_BASELINE.excluded_local_window,
            profile: profileName,
            sampleDays: profile.sample_days,
            timeZone: UK_TIME_ZONE,
        },
        tariffIntervalCount: intervals.length,
        availableProfileWeight,
        intervals,
    }
}

function unavailableStorageSavings(
    status: Exclude<StorageSavingsStatus, "available">,
    actualCostGbp: number,
    measuredKwh: number,
    pricedKwh: number,
): StorageSavingsEvaluation {
    return {
        status,
        actualAveragePencePerKwh: pricedKwh > 0
            ? (actualCostGbp * 100) / pricedKwh
            : null,
        actualCostGbp,
        withoutAlgorithmAveragePencePerKwh: null,
        withoutAlgorithmCostGbp: null,
        savedGbp: null,
        savedPercent: null,
        measuredKwh,
        pricedKwh,
        coverageRatio: measuredKwh > 0 ? pricedKwh / measuredKwh : 0,
    }
}

/**
 * Compare observed smart timing with the verified Orbis-only timing pattern.
 *
 * Each day's measured energy is held fixed. This isolates tariff shifting and
 * deliberately makes no claim that smart control reduced energy consumption.
 * Returned values retain full precision; presentation layers round only when
 * serializing or displaying them.
 */
export function evaluateStorageSavings(
    input: StorageSavingsEvaluationInput,
): StorageSavingsEvaluation {
    if (input.days.length === 0) {
        throw new Error("Storage-savings windows require at least one UK calendar date")
    }
    parseCalendarDate(input.smartControlStartDate)
    if (
        !Number.isFinite(input.minimumCoverageRatio)
        || input.minimumCoverageRatio < 0
        || input.minimumCoverageRatio > 1
    ) {
        throw new Error("minimumCoverageRatio must be between zero and one")
    }

    let measuredKwh = 0
    let pricedKwh = 0
    let actualCostGbp = 0
    let datesBeforeSmartControl = 0

    for (const day of input.days) {
        parseCalendarDate(day.localDate)
        if (
            !Number.isFinite(day.measuredKwh)
            || day.measuredKwh < 0
            || !Number.isFinite(day.pricedKwh)
            || day.pricedKwh < 0
            || day.pricedKwh > day.measuredKwh + PROFILE_WEIGHT_TOLERANCE
            || !Number.isFinite(day.actualCostGbp)
        ) {
            throw new Error(`Invalid storage-savings observation for ${day.localDate}`)
        }

        measuredKwh += day.measuredKwh
        pricedKwh += day.pricedKwh
        actualCostGbp += day.actualCostGbp
        if (day.localDate < input.smartControlStartDate) datesBeforeSmartControl += 1
    }

    if (datesBeforeSmartControl === input.days.length) {
        return unavailableStorageSavings(
            "not_applicable",
            actualCostGbp,
            measuredKwh,
            pricedKwh,
        )
    }
    if (datesBeforeSmartControl > 0) {
        return unavailableStorageSavings(
            "insufficient_data",
            actualCostGbp,
            measuredKwh,
            pricedKwh,
        )
    }
    if (measuredKwh <= 0) {
        return unavailableStorageSavings("no_usage", actualCostGbp, measuredKwh, pricedKwh)
    }

    const coverageRatio = pricedKwh / measuredKwh
    if (pricedKwh <= 0 || coverageRatio < input.minimumCoverageRatio) {
        return unavailableStorageSavings(
            "insufficient_data",
            actualCostGbp,
            measuredKwh,
            pricedKwh,
        )
    }

    let withoutAlgorithmCostGbp = 0

    for (const day of input.days) {
        if (day.measuredKwh <= 0) continue

        const dayCoverageRatio = day.pricedKwh / day.measuredKwh
        if (day.pricedKwh <= 0 || dayCoverageRatio < input.minimumCoverageRatio) {
            return unavailableStorageSavings(
                "insufficient_data",
                actualCostGbp,
                measuredKwh,
                pricedKwh,
            )
        }

        try {
            const estimate = estimateOrbisOnlyCost({
                localDate: day.localDate,
                actualKwh: day.pricedKwh,
                tariffIntervals: day.tariffIntervals,
            })
            withoutAlgorithmCostGbp += estimate.expectedOrbisCostGbp
        } catch (error) {
            if (error instanceof HeaterSavingsError) {
                return unavailableStorageSavings(
                    "insufficient_data",
                    actualCostGbp,
                    measuredKwh,
                    pricedKwh,
                )
            }
            throw error
        }
    }

    const savedGbp = withoutAlgorithmCostGbp - actualCostGbp
    return {
        status: "available",
        actualAveragePencePerKwh: (actualCostGbp * 100) / pricedKwh,
        actualCostGbp,
        withoutAlgorithmAveragePencePerKwh:
            (withoutAlgorithmCostGbp * 100) / pricedKwh,
        withoutAlgorithmCostGbp,
        savedGbp,
        savedPercent: withoutAlgorithmCostGbp > 0
            ? (savedGbp / withoutAlgorithmCostGbp) * 100
            : null,
        measuredKwh,
        pricedKwh,
        coverageRatio,
    }
}
