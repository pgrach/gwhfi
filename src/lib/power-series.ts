/**
 * Fill a single missing bucket in an otherwise continuous power trace.
 *
 * The worker sleeps after its network calls, so nominal one-minute readings can
 * occasionally land two buckets apart. Carrying a confirmed active load into
 * that one enclosed gap preserves the ON plateau and explicit OFF transition.
 * Unknown OFF periods, leading/trailing gaps, and longer gaps stay unknown.
 */
export function bridgeSingleBucketGaps(values: Array<number | null>): Array<number | null> {
    return values.map((value, index) => {
        if (value !== null || index === 0 || index === values.length - 1) return value

        const previous = values[index - 1]
        const next = values[index + 1]
        return previous !== null && previous > 0 && next !== null ? previous : null
    })
}
