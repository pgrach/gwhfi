export type DateViewMode = "today" | "tomorrow" | "7d" | "30d" | "custom"

export const EARLIEST_DASHBOARD_DATE = "2026-01-01"

export interface DateSelection {
    viewMode: DateViewMode
    customDate?: string
}

export function isValidCalendarDate(value: string | null): value is string {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false

    const [year, month, day] = value.split("-").map(Number)
    const normalized = new Date(Date.UTC(year, month - 1, day))
    return normalized.getUTCFullYear() === year
        && normalized.getUTCMonth() === month - 1
        && normalized.getUTCDate() === day
}

/** Map a calendar or URL date onto the dashboard's single-day views. */
export function classifyDateSelection(
    value: string | null,
    ukToday: string,
    ukTomorrow: string,
): DateSelection {
    if (!isValidCalendarDate(value) || value > ukTomorrow) {
        return { viewMode: "today" }
    }
    if (value === ukTomorrow) return { viewMode: "tomorrow" }
    if (value === ukToday) return { viewMode: "today" }
    return { viewMode: "custom", customDate: value }
}

export function isHistoricalCalendarDate(
    value: string | null,
    ukYesterday: string,
    earliestDate: string = EARLIEST_DASHBOARD_DATE,
): value is string {
    return isValidCalendarDate(value) && value >= earliestDate && value <= ukYesterday
}

/** Resolve URL state, with a single historical date taking precedence over a quick view. */
export function resolveDateView(
    selectedDate: string | null,
    requestedView: string | null,
    ukToday: string,
    ukTomorrow: string,
): DateSelection {
    if (isValidCalendarDate(selectedDate)) {
        if (selectedDate === ukTomorrow) return { viewMode: "tomorrow" }
        if (selectedDate === ukToday) return { viewMode: "today" }
        if (selectedDate >= EARLIEST_DASHBOARD_DATE && selectedDate < ukToday) {
            return { viewMode: "custom", customDate: selectedDate }
        }
    }

    if (requestedView === "tomorrow" || requestedView === "7d" || requestedView === "30d") {
        return { viewMode: requestedView }
    }
    return { viewMode: "today" }
}

export function calendarValueForView(
    viewMode: DateViewMode,
    ukToday: string,
    ukTomorrow: string,
    customDate: string,
): string {
    if (viewMode === "today") return ukToday
    if (viewMode === "tomorrow") return ukTomorrow
    if (viewMode === "custom") return customDate
    return ""
}
