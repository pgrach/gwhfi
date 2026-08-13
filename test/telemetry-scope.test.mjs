import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
    new URL("../src/lib/telemetry-scope.ts", import.meta.url),
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
    buildDownsampledReadingsRequest,
    buildEnergyCounterSeriesRequest,
    normalizeMeterDeviceId,
    resolveMeterDeviceId,
    siteOrLegacyFilter,
} = await import(moduleUrl)

test("normalizes configured meter IDs and ignores empty values", () => {
    assert.equal(normalizeMeterDeviceId("  meter-123  "), "meter-123")
    assert.equal(normalizeMeterDeviceId("   "), null)
    assert.equal(resolveMeterDeviceId("", " legacy-meter "), "legacy-meter")
})

test("uses the device-scoped RPC when a meter is configured", () => {
    assert.deepEqual(
        buildDownsampledReadingsRequest("start", "end", 60, "meter-123", "flat-1"),
        {
            functionName: "get_downsampled_readings_for_device",
            params: {
                start_time: "start",
                end_time: "end",
                bucket_seconds: 60,
                target_device_id: "meter-123",
                target_site_id: "flat-1",
            },
        }
    )
})

test("preserves the legacy RPC only while no meter is configured", () => {
    assert.deepEqual(
        buildDownsampledReadingsRequest("start", "end", 3600, null, null),
        {
            functionName: "get_downsampled_readings",
            params: {
                start_time: "start",
                end_time: "end",
                bucket_seconds: 3600,
            },
        }
    )
})

test("does not claim full scoping from a partial rollout configuration", () => {
    assert.equal(
        buildDownsampledReadingsRequest("start", "end", 60, "meter-123", null).functionName,
        "get_downsampled_readings"
    )
    assert.equal(
        buildDownsampledReadingsRequest("start", "end", 60, null, "flat-1").functionName,
        "get_downsampled_readings"
    )
})

test("site filter keeps matching legacy rows without admitting another device", () => {
    assert.equal(siteOrLegacyFilter("flat-1"), "site_id.eq.flat-1,site_id.is.null")
    assert.throws(() => siteOrLegacyFilter("flat-1,site_id.not.is.null"), /simple slug/)
})

test("builds the compact counter RPC only with a complete site and meter scope", () => {
    assert.deepEqual(
        buildEnergyCounterSeriesRequest("start", "end", 300, "flat-1", "meter-123"),
        {
            functionName: "get_energy_counter_series_for_device",
            params: {
                start_time: "start",
                end_time: "end",
                bucket_seconds: 300,
                target_site_id: "flat-1",
                target_device_id: "meter-123",
            },
        }
    )
    assert.throws(
        () => buildEnergyCounterSeriesRequest("start", "end", 300, null, "meter-123"),
        /requires both telemetry site and meter IDs/
    )
})

test("automatic GitHub ingestion stays disabled", async () => {
    const workflow = await readFile(
        new URL("../.github/workflows/ingest_energy.yaml", import.meta.url),
        "utf8"
    )
    assert.match(workflow, /workflow_dispatch:/)
    assert.doesNotMatch(workflow, /^\s+schedule:/m)
    assert.doesNotMatch(workflow, /^\s+push:/m)
    assert.doesNotMatch(workflow, /cloud_worker_oneshot\.py/)
})
