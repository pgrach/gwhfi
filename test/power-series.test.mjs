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
const { bridgeSingleBucketGaps, collectScheduledPeriods } = await import(moduleUrl)

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
        { raw_time: 0, isScheduled: false },
        { raw_time: 30 * 60_000, isScheduled: true },
        { raw_time: 60 * 60_000, isScheduled: true },
        { raw_time: 90 * 60_000, isScheduled: false },
        { raw_time: 120 * 60_000, isScheduled: true },
        { raw_time: 150 * 60_000, isScheduled: false },
    ], 30), [
        { start: 30 * 60_000, end: 90 * 60_000 },
        { start: 120 * 60_000, end: 150 * 60_000 },
    ])
})

test("handles schedule windows at the range boundaries", () => {
    assert.deepEqual(collectScheduledPeriods([
        { raw_time: 0, isScheduled: true },
        { raw_time: 30 * 60_000, isScheduled: false },
    ], 30), [{ start: 0, end: 30 * 60_000 }])

    assert.deepEqual(collectScheduledPeriods([
        { raw_time: 23.5 * 60 * 60_000, isScheduled: true },
        { raw_time: (24 * 60 - 1) * 60_000, isScheduled: true },
    ], 1), [{ start: 23.5 * 60 * 60_000, end: 24 * 60 * 60_000 }])

    assert.deepEqual(collectScheduledPeriods([
        { raw_time: (24 * 60 - 1) * 60_000, isScheduled: true },
    ], 1), [{ start: (24 * 60 - 1) * 60_000, end: 24 * 60 * 60_000 }])
})

test("keeps repeated DST clock times distinct by their timestamps", () => {
    const firstOneThirty = Date.parse("2026-10-25T00:30:00Z")
    const secondOneThirty = Date.parse("2026-10-25T01:30:00Z")

    assert.deepEqual(collectScheduledPeriods([
        { raw_time: firstOneThirty, isScheduled: true },
        { raw_time: secondOneThirty, isScheduled: false },
    ], 60), [{ start: firstOneThirty, end: secondOneThirty }])
    assert.notEqual(firstOneThirty, secondOneThirty)
})
