import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
    new URL("../src/lib/date-selection.ts", import.meta.url),
    "utf8"
)
const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
const {
    calendarValueForView,
    classifyDateSelection,
    isHistoricalCalendarDate,
    isValidCalendarDate,
    resolveDateView,
} = await import(moduleUrl)

const today = "2026-08-12"
const tomorrow = "2026-08-13"

test("accepts real calendar dates and rejects normalized or malformed dates", () => {
    assert.equal(isValidCalendarDate("2024-02-29"), true)
    assert.equal(isValidCalendarDate("2026-02-29"), false)
    assert.equal(isValidCalendarDate("2026-02-30"), false)
    assert.equal(isValidCalendarDate("12/08/2026"), false)
})

test("maps historical, today, and tomorrow dates to the matching view", () => {
    assert.deepEqual(classifyDateSelection("2026-08-11", today, tomorrow), {
        viewMode: "custom",
        customDate: "2026-08-11",
    })
    assert.deepEqual(classifyDateSelection(today, today, tomorrow), { viewMode: "today" })
    assert.deepEqual(classifyDateSelection(tomorrow, today, tomorrow), { viewMode: "tomorrow" })
})

test("falls back to today for missing, invalid, or unsupported future dates", () => {
    assert.deepEqual(classifyDateSelection(null, today, tomorrow), { viewMode: "today" })
    assert.deepEqual(classifyDateSelection("2026-02-30", today, tomorrow), { viewMode: "today" })
    assert.deepEqual(classifyDateSelection("2026-08-14", today, tomorrow), { viewMode: "today" })
})

test("accepts only complete historical days for paid-price queries", () => {
    assert.equal(isHistoricalCalendarDate("2026-08-11", "2026-08-11"), true)
    assert.equal(isHistoricalCalendarDate("2026-08-12", "2026-08-11"), false)
    assert.equal(isHistoricalCalendarDate("2026-02-30", "2026-08-11"), false)
    assert.equal(isHistoricalCalendarDate("2025-12-31", "2026-08-11"), false)
})

test("resolves historical dates and quick-view URL state consistently", () => {
    assert.deepEqual(resolveDateView("2026-08-11", "30d", today, tomorrow), {
        viewMode: "custom",
        customDate: "2026-08-11",
    })
    assert.deepEqual(resolveDateView(null, "tomorrow", today, tomorrow), { viewMode: "tomorrow" })
    assert.deepEqual(resolveDateView(null, "7d", today, tomorrow), { viewMode: "7d" })
    assert.deepEqual(resolveDateView("2026-02-30", "30d", today, tomorrow), { viewMode: "30d" })
    assert.deepEqual(resolveDateView("2025-12-31", null, today, tomorrow), { viewMode: "today" })
    assert.deepEqual(resolveDateView(null, "unsupported", today, tomorrow), { viewMode: "today" })
})

test("shows a date only for single-day views", () => {
    assert.equal(calendarValueForView("today", today, tomorrow, "2026-08-11"), today)
    assert.equal(calendarValueForView("tomorrow", today, tomorrow, "2026-08-11"), tomorrow)
    assert.equal(calendarValueForView("custom", today, tomorrow, "2026-08-11"), "2026-08-11")
    assert.equal(calendarValueForView("7d", today, tomorrow, "2026-08-11"), "")
    assert.equal(calendarValueForView("30d", today, tomorrow, "2026-08-11"), "")
})
