export interface AnalyticsTimeRange {
    startMs: number
    endMs: number
}

export interface AnalyticsRangePlan {
    recent: AnalyticsTimeRange
    selectedSeparate: AnalyticsTimeRange | null
}

function isValidRange(range: AnalyticsTimeRange): boolean {
    return Number.isFinite(range.startMs)
        && Number.isFinite(range.endMs)
        && range.startMs < range.endMs
}

export function planAnalyticsRanges(
    recent: AnalyticsTimeRange,
    selected: AnalyticsTimeRange | null,
): AnalyticsRangePlan {
    if (!isValidRange(recent) || (selected !== null && !isValidRange(selected))) {
        throw new Error("Analytics ranges must have finite, increasing boundaries")
    }

    const selectedIsInsideRecent = selected !== null
        && selected.startMs >= recent.startMs
        && selected.endMs <= recent.endMs

    return {
        recent,
        selectedSeparate: selected && !selectedIsInsideRecent ? selected : null,
    }
}
