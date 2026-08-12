import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
    new URL("../src/lib/power-series.ts", import.meta.url),
    "utf8"
)
const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
const { bridgeSingleBucketGaps, collectScheduledPeriods, formatScheduleRangeEnd } = await import(moduleUrl)

test("bridges one enclosed missing minute while the heater is active", () => {
    assert.deepEqual(
        bridgeSingleBucketGaps([1500, null, 1490]),
        [1500, 1500, 1490]
    )
    assert.deepEqual(
        bridgeSingleBucketGaps([1500, null, 0]),
        [1500, 1500, 0]
    )
})

test("does not invent OFF readings or extrapolate beyond observations", () => {
    assert.deepEqual(bridgeSingleBucketGaps([0, null, 1500]), [0, null, 1500])
    assert.deepEqual(bridgeSingleBucketGaps([0, null, 0]), [0, null, 0])
    assert.deepEqual(bridgeSingleBucketGaps([null, 1500]), [null, 1500])
    assert.deepEqual(bridgeSingleBucketGaps([1500, null]), [1500, null])
})

test("leaves longer outages visible and does not mutate its input", () => {
    const values = [1500, null, null, 0]
    assert.deepEqual(bridgeSingleBucketGaps(values), values)
    assert.deepEqual(values, [1500, null, null, 0])
})

test("reconstructs channels independently", () => {
    const peak = bridgeSingleBucketGaps([1200, null, 1180])
    const storage = bridgeSingleBucketGaps([0, null, 3100])

    assert.deepEqual(peak, [1200, 1200, 1180])
    assert.deepEqual(storage, [0, null, 3100])
})

test("merges adjacent scheduled buckets into continuous windows", () => {
    assert.deepEqual(collectScheduledPeriods([
        { timestamp: "00:00", isScheduled: false },
        { timestamp: "00:30", isScheduled: true },
        { timestamp: "01:00", isScheduled: true },
        { timestamp: "01:30", isScheduled: false },
        { timestamp: "02:00", isScheduled: true },
        { timestamp: "02:30", isScheduled: false },
    ]), [
        { start: "00:30", end: "01:30" },
        { start: "02:00", end: "02:30" },
    ])
})

test("handles schedule windows at the range boundaries", () => {
    assert.deepEqual(collectScheduledPeriods([
        { timestamp: "00:00", isScheduled: true },
        { timestamp: "00:30", isScheduled: false },
    ]), [{ start: "00:00", end: "00:30" }])

    assert.deepEqual(collectScheduledPeriods([
        { timestamp: "23:30", isScheduled: true },
        { timestamp: "23:59", isScheduled: true },
    ], "24:00"), [{ start: "23:30", end: "24:00" }])

    assert.deepEqual(collectScheduledPeriods([
        { timestamp: "23:59", isScheduled: true },
    ], "24:00"), [{ start: "23:59", end: "24:00" }])
})

test("formats an exclusive schedule-band endpoint one bucket later", () => {
    assert.equal(formatScheduleRangeEnd(Date.parse("2026-08-12T22:59:00Z"), 1), "00:00")
    assert.equal(formatScheduleRangeEnd(Date.parse("2026-08-12T22:00:00Z"), 60), "13/08, 00:00")
})
