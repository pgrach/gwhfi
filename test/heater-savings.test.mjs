import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import test from "node:test"

const ts = createRequire(import.meta.url)("typescript")

const [source, baselineSource] = await Promise.all([
    readFile(new URL("../src/lib/heater-savings.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/data/orbis-baseline-v1.json", import.meta.url), "utf8"),
])
const baselineArtifact = JSON.parse(baselineSource)
const testableSource = source.replace(
    'import baselineArtifact from "../data/orbis-baseline-v1.json"',
    `const baselineArtifact = ${JSON.stringify(baselineArtifact)}`,
)
const { outputText } = ts.transpileModule(testableSource, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
const {
    evaluateStorageSavings,
    estimateOrbisOnlyCost,
    HeaterSavingsError,
    ORBIS_BASELINE,
    ORBIS_BASELINE_METADATA,
    validateOrbisBaseline,
} = await import(moduleUrl)

const HALF_HOUR_MS = 30 * 60 * 1_000
const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
})

function localParts(timestampMs) {
    const parts = Object.fromEntries(
        formatter
            .formatToParts(new Date(timestampMs))
            .filter((part) => part.type !== "literal")
            .map((part) => [part.type, part.value]),
    )
    return {
        date: `${parts.year}-${parts.month}-${parts.day}`,
        time: `${parts.hour}:${parts.minute}`,
    }
}

function tariffDay(localDate, rateForInterval = () => 20) {
    const [year, month, day] = localDate.split("-").map(Number)
    const nominalUtcMidnight = Date.UTC(year, month - 1, day)
    const intervals = []

    for (
        let fromMs = nominalUtcMidnight - (3 * 60 * 60 * 1_000);
        fromMs < nominalUtcMidnight + (27 * 60 * 60 * 1_000);
        fromMs += HALF_HOUR_MS
    ) {
        const local = localParts(fromMs)
        if (local.date !== localDate) continue
        intervals.push({
            valid_from: new Date(fromMs).toISOString(),
            valid_to: new Date(fromMs + HALF_HOUR_MS).toISOString(),
            value_inc_vat: rateForInterval({ fromMs, ...local, index: intervals.length }),
        })
    }

    return intervals
}

function approximatelyEqual(actual, expected, tolerance = 1e-10) {
    assert.ok(
        Math.abs(actual - expected) <= tolerance,
        `expected ${actual} to be within ${tolerance} of ${expected}`,
    )
}

test("baseline profiles are normalized and omit the fixed 16:00-19:00 cutoff", () => {
    assert.doesNotThrow(() => validateOrbisBaseline())

    for (const profileName of ["all", "weekday", "weekend"]) {
        const entries = Object.entries(ORBIS_BASELINE.profiles[profileName].weights)
        approximatelyEqual(
            entries.reduce((sum, [, weight]) => sum + weight, 0),
            1,
            1e-6,
        )
        assert.equal(entries.length, 42)
        assert.equal(
            entries.some(([slot]) => slot >= "16:00" && slot < "19:00"),
            false,
        )
    }

    assert.equal(ORBIS_BASELINE_METADATA.artifactVersion, ORBIS_BASELINE.version)
    assert.equal(ORBIS_BASELINE_METADATA.sampleDays.weekday, 49)
    assert.equal(ORBIS_BASELINE_METADATA.sampleDays.weekend, 20)
})

test("selects weekday and weekend profiles from the UK calendar date", () => {
    const monday = estimateOrbisOnlyCost({
        localDate: "2026-11-02",
        actualKwh: 6,
        tariffIntervals: tariffDay("2026-11-02"),
    })
    const sunday = estimateOrbisOnlyCost({
        localDate: "2026-11-01",
        actualKwh: 6,
        tariffIntervals: tariffDay("2026-11-01"),
    })

    assert.equal(monday.profile, "weekday")
    assert.equal(monday.baseline.profile, "weekday")
    assert.equal(monday.baseline.sampleDays, 49)
    assert.equal(sunday.profile, "weekend")
    assert.equal(sunday.baseline.profile, "weekend")
    assert.equal(sunday.baseline.sampleDays, 20)
})

test("rejects incomplete tariff coverage even when the missing slot has zero baseline weight", () => {
    const localDate = "2026-11-02"
    const completeRates = tariffDay(localDate)
    const missingCutoffRate = completeRates.filter((interval) => (
        localParts(Date.parse(interval.valid_from)).time !== "17:00"
    ))

    assert.throws(
        () => estimateOrbisOnlyCost({
            localDate,
            actualKwh: 6,
            tariffIntervals: missingCutoffRate,
        }),
        (error) => (
            error instanceof HeaterSavingsError
            && error.code === "incomplete_tariff_coverage"
            && error.details.expectedIntervalCount === 48
            && error.details.receivedIntervalCount === 47
        ),
    )
})

test("renormalizes around missing local slots on the 23-hour spring DST day", () => {
    const localDate = "2026-03-29"
    const estimate = estimateOrbisOnlyCost({
        localDate,
        actualKwh: 7.25,
        tariffIntervals: tariffDay(localDate),
    })

    assert.equal(estimate.tariffIntervalCount, 46)
    assert.equal(estimate.intervals.some((interval) => interval.localTime === "01:00"), false)
    assert.equal(estimate.intervals.some((interval) => interval.localTime === "01:30"), false)
    assert.ok(estimate.availableProfileWeight < 1)
    approximatelyEqual(
        estimate.intervals.reduce((sum, interval) => sum + interval.normalizedWeight, 0),
        1,
    )
    approximatelyEqual(
        estimate.intervals.reduce((sum, interval) => sum + interval.expectedKwh, 0),
        7.25,
    )
})

test("allocates both repeated local slots on the 25-hour autumn DST day", () => {
    const localDate = "2026-10-25"
    const estimate = estimateOrbisOnlyCost({
        localDate,
        actualKwh: 7.25,
        tariffIntervals: tariffDay(localDate),
    })

    assert.equal(estimate.tariffIntervalCount, 50)
    assert.equal(estimate.intervals.filter((interval) => interval.localTime === "01:00").length, 2)
    assert.equal(estimate.intervals.filter((interval) => interval.localTime === "01:30").length, 2)
    assert.ok(estimate.availableProfileWeight > 1)
    approximatelyEqual(
        estimate.intervals.reduce((sum, interval) => sum + interval.normalizedWeight, 0),
        1,
    )
    approximatelyEqual(
        estimate.intervals.reduce((sum, interval) => sum + interval.expectedKwh, 0),
        7.25,
    )
})

test("preserves negative Agile rates in cost and average-rate estimates", () => {
    const estimate = estimateOrbisOnlyCost({
        localDate: "2026-11-02",
        actualKwh: 8,
        tariffIntervals: tariffDay("2026-11-02", () => -5.5),
    })

    approximatelyEqual(estimate.expectedOrbisCostGbp, -0.44)
    approximatelyEqual(estimate.expectedOrbisAveragePencePerKwh, -5.5)
    approximatelyEqual(
        estimate.intervals.reduce((sum, interval) => sum + interval.expectedKwh, 0),
        estimate.actualKwh,
    )
})

test("zero energy produces a complete zero-cost estimate", () => {
    const estimate = estimateOrbisOnlyCost({
        localDate: "2026-11-02",
        actualKwh: 0,
        tariffIntervals: tariffDay("2026-11-02", () => 37.5),
    })

    assert.equal(estimate.expectedOrbisCostGbp, 0)
    assert.equal(estimate.expectedOrbisAveragePencePerKwh, null)
    approximatelyEqual(
        estimate.intervals.reduce((sum, interval) => sum + interval.expectedKwh, 0),
        0,
    )
})

test("rejects invalid energy and malformed Agile intervals", () => {
    assert.throws(
        () => estimateOrbisOnlyCost({
            localDate: "2026-11-02",
            actualKwh: -1,
            tariffIntervals: tariffDay("2026-11-02"),
        }),
        (error) => error instanceof HeaterSavingsError && error.code === "invalid_actual_kwh",
    )

    const malformed = tariffDay("2026-11-02")
    malformed[0] = { ...malformed[0], valid_to: malformed[0].valid_from }
    assert.throws(
        () => estimateOrbisOnlyCost({
            localDate: "2026-11-02",
            actualKwh: 1,
            tariffIntervals: malformed,
        }),
        (error) => error instanceof HeaterSavingsError && error.code === "invalid_tariff_interval",
    )
})

function savingsDay(localDate, overrides = {}) {
    return {
        localDate,
        measuredKwh: 4,
        pricedKwh: 4,
        actualCostGbp: 0.4,
        tariffIntervals: tariffDay(localDate, () => 20),
        ...overrides,
    }
}

function evaluate(days) {
    return evaluateStorageSavings({
        days,
        smartControlStartDate: "2026-08-12",
        minimumCoverageRatio: 0.99,
    })
}

test("does not claim savings before smart control began", () => {
    const result = evaluate([
        savingsDay("2026-08-10", { tariffIntervals: [] }),
        savingsDay("2026-08-11", { tariffIntervals: [] }),
    ])

    assert.equal(result.status, "not_applicable")
    assert.equal(result.withoutAlgorithmCostGbp, null)
    assert.equal(result.savedGbp, null)
})

test("does not claim savings for a window spanning control regimes", () => {
    const result = evaluate([
        savingsDay("2026-08-11", { tariffIntervals: [] }),
        savingsDay("2026-08-12", { tariffIntervals: [] }),
    ])

    assert.equal(result.status, "insufficient_data")
    assert.equal(result.savedGbp, null)
})

test("reports no usage without requiring tariff data", () => {
    const result = evaluate([
        savingsDay("2026-11-02", {
            measuredKwh: 0,
            pricedKwh: 0,
            actualCostGbp: 0,
            tariffIntervals: [],
        }),
    ])

    assert.equal(result.status, "no_usage")
    assert.equal(result.actualAveragePencePerKwh, null)
    assert.equal(result.coverageRatio, 0)
})

test("withholds savings when energy or tariff coverage is incomplete", () => {
    const lowEnergyCoverage = evaluate([
        savingsDay("2026-11-02", { measuredKwh: 4, pricedKwh: 3.9 }),
    ])
    assert.equal(lowEnergyCoverage.status, "insufficient_data")

    const incompleteTariffs = tariffDay("2026-11-02").slice(1)
    const incompleteTariffCoverage = evaluate([
        savingsDay("2026-11-02", { tariffIntervals: incompleteTariffs }),
    ])
    assert.equal(incompleteTariffCoverage.status, "insufficient_data")
})

test("aggregates multiple days at full precision before presentation rounding", () => {
    const result = evaluate([
        savingsDay("2026-11-02", {
            measuredKwh: 4,
            pricedKwh: 4,
            actualCostGbp: 0.2000004,
            tariffIntervals: tariffDay("2026-11-02", () => 20),
        }),
        savingsDay("2026-11-03", {
            measuredKwh: 6,
            pricedKwh: 6,
            actualCostGbp: 0.6000004,
            tariffIntervals: tariffDay("2026-11-03", () => 30),
        }),
    ])

    assert.equal(result.status, "available")
    approximatelyEqual(result.measuredKwh, 10)
    approximatelyEqual(result.pricedKwh, 10)
    approximatelyEqual(result.actualCostGbp, 0.8000008)
    approximatelyEqual(result.actualAveragePencePerKwh, 8.000008)
    approximatelyEqual(result.withoutAlgorithmCostGbp, 2.6)
    approximatelyEqual(result.withoutAlgorithmAveragePencePerKwh, 26)
    approximatelyEqual(result.savedGbp, 1.7999992)
    approximatelyEqual(result.savedPercent, (1.7999992 / 2.6) * 100)
})
