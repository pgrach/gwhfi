import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
    new URL("../src/lib/downsampled-readings.ts", import.meta.url),
    "utf8"
)
const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
const { fetchCompleteDownsampledRange } = await import(moduleUrl)

const MINUTE_MS = 60_000

function rowsForRange(startIso, endIso, { inclusiveEnd = false } = {}) {
    const startMs = Date.parse(startIso)
    const endMs = Date.parse(endIso)
    const rows = []
    const finalMs = inclusiveEnd ? endMs : endMs - 1

    for (let bucketMs = startMs; bucketMs <= finalMs; bucketMs += MINUTE_MS) {
        for (const channel of [0, 1]) {
            rows.push({
                bucket_time: new Date(bucketMs).toISOString(),
                channel,
                avg_power: bucketMs + channel,
            })
        }
    }
    return rows
}

test("fetches a complete two-channel day without hitting the 1000-row cap", async () => {
    const startMs = Date.parse("2026-08-13T00:00:00.000Z")
    const endMs = startMs + 24 * 60 * MINUTE_MS
    const calls = []

    const result = await fetchCompleteDownsampledRange(
        startMs,
        endMs,
        60,
        async (startIso, endIso) => {
            calls.push([startIso, endIso])
            const complete = rowsForRange(startIso, endIso)
            return { data: complete.slice(0, 1000), error: null }
        },
    )

    assert.equal(calls.length, 4)
    assert.equal(result.errors.length, 0)
    assert.equal(result.data.length, 2880)
    assert.equal(result.data[0].bucket_time, "2026-08-13T00:00:00.000Z")
    assert.equal(result.data.at(-1).bucket_time, "2026-08-13T23:59:00.000Z")
})

test("recursively subdivides a chunk whenever the response reaches its row cap", async () => {
    const startMs = Date.parse("2026-08-13T00:00:00.000Z")
    const endMs = startMs + 6 * MINUTE_MS
    let calls = 0

    const result = await fetchCompleteDownsampledRange(
        startMs,
        endMs,
        60,
        async (startIso, endIso) => {
            calls += 1
            return { data: rowsForRange(startIso, endIso).slice(0, 4), error: null }
        },
        { rowLimit: 4, bucketsPerChunk: 6 },
    )

    assert.ok(calls > 1)
    assert.equal(result.errors.length, 0)
    assert.equal(result.data.length, 12)
})

test("de-duplicates inclusive legacy boundaries and keeps the later full bucket", async () => {
    const startMs = Date.parse("2026-08-13T00:00:00.000Z")
    const endMs = startMs + 4 * MINUTE_MS

    const result = await fetchCompleteDownsampledRange(
        startMs,
        endMs,
        60,
        async (startIso, endIso) => {
            const chunkStartMs = Date.parse(startIso)
            const rows = rowsForRange(startIso, endIso, { inclusiveEnd: true })
                .map((row) => ({ ...row, avg_power: chunkStartMs }))
            return { data: rows, error: null }
        },
        { bucketsPerChunk: 2 },
    )

    assert.equal(result.data.length, 10)
    const sharedBoundary = result.data.find((row) => (
        row.bucket_time === "2026-08-13T00:02:00.000Z" && row.channel === 0
    ))
    assert.equal(sharedBoundary.avg_power, startMs + 2 * MINUTE_MS)
})

test("returns successful chunks while surfacing a failed chunk", async () => {
    const startMs = Date.parse("2026-08-13T00:00:00.000Z")
    const endMs = startMs + 4 * MINUTE_MS
    const failure = new Error("RPC unavailable")

    const result = await fetchCompleteDownsampledRange(
        startMs,
        endMs,
        60,
        async (startIso, endIso) => {
            if (Date.parse(startIso) >= startMs + 2 * MINUTE_MS) {
                return { data: null, error: failure }
            }
            return { data: rowsForRange(startIso, endIso), error: null }
        },
        { bucketsPerChunk: 2 },
    )

    assert.deepEqual(result.errors, [failure])
    assert.equal(result.data.length, 4)
})

test("caps concurrent chunk requests, including recursive subdivisions", async () => {
    const startMs = Date.parse("2026-08-13T00:00:00.000Z")
    const endMs = startMs + 24 * MINUTE_MS
    let inFlight = 0
    let maximumInFlight = 0

    const result = await fetchCompleteDownsampledRange(
        startMs,
        endMs,
        60,
        async (startIso, endIso) => {
            inFlight += 1
            maximumInFlight = Math.max(maximumInFlight, inFlight)
            await new Promise((resolve) => setTimeout(resolve, 5))
            inFlight -= 1
            return { data: rowsForRange(startIso, endIso).slice(0, 4), error: null }
        },
        { rowLimit: 4, bucketsPerChunk: 6, maxConcurrency: 3 },
    )

    assert.equal(result.errors.length, 0)
    assert.equal(result.data.length, 48)
    assert.equal(maximumInFlight, 3)
})
