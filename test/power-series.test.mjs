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
const { bridgeSingleBucketGaps } = await import(moduleUrl)

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
