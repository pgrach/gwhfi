export const DOWNSAMPLED_RPC_ROW_LIMIT = 1000
export const DOWNSAMPLED_BUCKETS_PER_CHUNK = 360
export const DOWNSAMPLED_MAX_CONCURRENCY = 4

export interface DownsampledRowIdentity {
    bucket_time: string
    channel: number
}

export interface DownsampledChunkResponse<T> {
    data: T[] | null
    error: unknown
}

export interface DownsampledRangeResult<T> {
    data: T[]
    errors: unknown[]
}

interface DownsampledFetchOptions {
    rowLimit?: number
    bucketsPerChunk?: number
    maxConcurrency?: number
}

function mergeChronologicalRows<T extends DownsampledRowIdentity>(rows: T[]): T[] {
    const byBucketAndChannel = new Map<string, T>()

    for (const row of rows) {
        const bucketMs = Date.parse(row.bucket_time)
        const bucketKey = Number.isFinite(bucketMs) ? bucketMs : row.bucket_time
        // Later chunks win at a shared boundary. This matters while the legacy
        // RPC still treats end_time as inclusive: its earlier chunk contains a
        // partial boundary bucket, while the later chunk contains the full one.
        byBucketAndChannel.set(`${bucketKey}:${row.channel}`, row)
    }

    return [...byBucketAndChannel.values()].sort((left, right) => {
        const leftMs = Date.parse(left.bucket_time)
        const rightMs = Date.parse(right.bucket_time)
        if (Number.isFinite(leftMs) && Number.isFinite(rightMs) && leftMs !== rightMs) {
            return leftMs - rightMs
        }
        if (left.bucket_time !== right.bucket_time) {
            return left.bucket_time.localeCompare(right.bucket_time)
        }
        return left.channel - right.channel
    })
}

export async function fetchCompleteDownsampledRange<T extends DownsampledRowIdentity>(
    startMs: number,
    endMs: number,
    bucketSeconds: number,
    fetchChunk: (startIso: string, endIso: string) => Promise<DownsampledChunkResponse<T>>,
    options: DownsampledFetchOptions = {},
): Promise<DownsampledRangeResult<T>> {
    const rowLimit = options.rowLimit ?? DOWNSAMPLED_RPC_ROW_LIMIT
    const bucketsPerChunk = options.bucketsPerChunk ?? DOWNSAMPLED_BUCKETS_PER_CHUNK
    const maxConcurrency = options.maxConcurrency ?? DOWNSAMPLED_MAX_CONCURRENCY
    const bucketMs = bucketSeconds * 1000

    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || startMs >= endMs) {
        throw new Error("Downsampled range must have finite, increasing boundaries")
    }
    if (!Number.isInteger(bucketSeconds) || bucketSeconds < 1) {
        throw new Error("Downsample bucket must be a positive whole number of seconds")
    }
    if (!Number.isInteger(rowLimit) || rowLimit < 2) {
        throw new Error("Downsample row limit must be at least 2")
    }
    if (!Number.isInteger(bucketsPerChunk) || bucketsPerChunk < 1) {
        throw new Error("Downsample chunk size must contain at least one bucket")
    }
    if (!Number.isInteger(maxConcurrency) || maxConcurrency < 1) {
        throw new Error("Downsample concurrency must be a positive whole number")
    }

    const fetchBoundedChunk = async (
        chunkStartMs: number,
        chunkEndMs: number,
    ): Promise<DownsampledRangeResult<T>> => {
        const response = await fetchChunk(
            new Date(chunkStartMs).toISOString(),
            new Date(chunkEndMs).toISOString(),
        )

        if (response.error) {
            return { data: [], errors: [response.error] }
        }

        const rows = response.data ?? []
        if (rows.length < rowLimit) {
            return { data: rows, errors: [] }
        }

        const durationMs = chunkEndMs - chunkStartMs
        if (durationMs <= bucketMs) {
            return {
                data: [],
                errors: [new Error("Downsampled RPC row cap was reached within one bucket")],
            }
        }

        let splitMs = chunkStartMs
            + Math.floor(durationMs / bucketMs / 2) * bucketMs
        if (splitMs <= chunkStartMs) splitMs = chunkStartMs + bucketMs
        if (splitMs >= chunkEndMs) splitMs = chunkStartMs + Math.floor(durationMs / 2)

        // Recurse serially inside a worker so cap-triggered subdivision cannot
        // fan out beyond the global worker limit below.
        const left = await fetchBoundedChunk(chunkStartMs, splitMs)
        const right = await fetchBoundedChunk(splitMs, chunkEndMs)
        return {
            data: [...left.data, ...right.data],
            errors: [...left.errors, ...right.errors],
        }
    }

    const ranges: Array<{ startMs: number; endMs: number }> = []
    const maximumChunkMs = bucketsPerChunk * bucketMs
    for (let chunkStartMs = startMs; chunkStartMs < endMs; chunkStartMs += maximumChunkMs) {
        const chunkEndMs = Math.min(chunkStartMs + maximumChunkMs, endMs)
        ranges.push({ startMs: chunkStartMs, endMs: chunkEndMs })
    }

    const chunks = new Array<DownsampledRangeResult<T>>(ranges.length)
    let nextRangeIndex = 0
    const worker = async () => {
        while (true) {
            const rangeIndex = nextRangeIndex
            nextRangeIndex += 1
            if (rangeIndex >= ranges.length) return

            const range = ranges[rangeIndex]
            chunks[rangeIndex] = await fetchBoundedChunk(range.startMs, range.endMs)
        }
    }
    await Promise.all(
        Array.from(
            { length: Math.min(maxConcurrency, ranges.length) },
            () => worker(),
        ),
    )

    return {
        data: mergeChronologicalRows(chunks.flatMap((chunk) => chunk.data)),
        errors: chunks.flatMap((chunk) => chunk.errors),
    }
}
