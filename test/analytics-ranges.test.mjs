import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
    new URL("../src/lib/analytics-ranges.ts", import.meta.url),
    "utf8"
)
const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
const { planAnalyticsRanges } = await import(moduleUrl)

test("reuses the rolling range for a selected day already inside it", () => {
    assert.deepEqual(
        planAnalyticsRanges(
            { startMs: 1_000, endMs: 4_000 },
            { startMs: 2_000, endMs: 3_000 },
        ),
        {
            recent: { startMs: 1_000, endMs: 4_000 },
            selectedSeparate: null,
        }
    )
})

test("fetches only the isolated selected day when it predates the rolling range", () => {
    assert.deepEqual(
        planAnalyticsRanges(
            { startMs: 10_000, endMs: 20_000 },
            { startMs: 1_000, endMs: 2_000 },
        ),
        {
            recent: { startMs: 10_000, endMs: 20_000 },
            selectedSeparate: { startMs: 1_000, endMs: 2_000 },
        }
    )
})

test("rejects invalid ranges instead of issuing unbounded queries", () => {
    assert.throws(
        () => planAnalyticsRanges({ startMs: 2_000, endMs: 1_000 }, null),
        /finite, increasing boundaries/
    )
})
