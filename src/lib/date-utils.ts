/**
 * UK Date Boundary Utilities
 * 
 * Handles timezone-aware date boundary calculations for Europe/London,
 * correctly accounting for GMT/BST transitions.
 */

const UK_TIME_ZONE = 'Europe/London'

interface DateParts {
    year: number
    month: number
    day: number
}

function getUkDatePartsForInstant(date: Date): DateParts {
    const formatter = new Intl.DateTimeFormat('en-GB', {
        timeZone: UK_TIME_ZONE,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    })
    const parts = formatter.formatToParts(date)

    return {
        year: Number(parts.find((p) => p.type === 'year')?.value),
        month: Number(parts.find((p) => p.type === 'month')?.value),
        day: Number(parts.find((p) => p.type === 'day')?.value),
    }
}

function getUkOffsetMinutesAtInstant(instantUtc: Date): number {
    const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: UK_TIME_ZONE,
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })

    const parts = formatter.formatToParts(instantUtc)
    const hour = Number(parts.find((p) => p.type === 'hour')?.value)
    const minute = Number(parts.find((p) => p.type === 'minute')?.value)
    const second = Number(parts.find((p) => p.type === 'second')?.value)

    const utcHour = instantUtc.getUTCHours()
    const utcMinute = instantUtc.getUTCMinutes()
    const utcSecond = instantUtc.getUTCSeconds()

    const localTotalMinutes = hour * 60 + minute + second / 60
    const utcTotalMinutes = utcHour * 60 + utcMinute + utcSecond / 60

    let diff = localTotalMinutes - utcTotalMinutes
    if (diff > 720) diff -= 1440
    if (diff < -720) diff += 1440

    return diff
}

function shiftYmd(parts: DateParts, dayOffset: number): DateParts {
    const shifted = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + dayOffset, 12, 0, 0))
    return {
        year: shifted.getUTCFullYear(),
        month: shifted.getUTCMonth() + 1,
        day: shifted.getUTCDate(),
    }
}

function getUkMidnightUtc(parts: DateParts): Date {
    const tentativeUtc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 0, 0, 0, 0))
    const offsetMinutes = getUkOffsetMinutesAtInstant(tentativeUtc)
    return new Date(tentativeUtc.getTime() - offsetMinutes * 60 * 1000)
}

function parseYyyyMmDd(dateStr: string): DateParts {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr)
    if (!match) {
        throw new Error(`Invalid date format: ${dateStr}`)
    }

    const year = Number(match[1])
    const month = Number(match[2])
    const day = Number(match[3])

    const normalized = new Date(Date.UTC(year, month - 1, day, 12, 0, 0))
    if (
        normalized.getUTCFullYear() !== year ||
        normalized.getUTCMonth() + 1 !== month ||
        normalized.getUTCDate() !== day
    ) {
        throw new Error(`Invalid calendar date: ${dateStr}`)
    }

    return { year, month, day }
}

function toYyyyMmDd(parts: DateParts): string {
    return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`
}

/**
 * Get UK (Europe/London) calendar date as YYYY-MM-DD.
 *
 * @param dayOffset - Number of days offset from UK today (e.g., 0 = today, -1 = yesterday)
 */
export function getUKDateString(dayOffset: number = 0): string {
    const todayUk = getUkDatePartsForInstant(new Date())
    return toYyyyMmDd(shiftYmd(todayUk, dayOffset))
}

/**
 * Get UK (Europe/London) date boundaries in UTC.
 * Ensures "today" always means UK midnight-to-midnight regardless of viewer's timezone.
 * 
 * @param dayOffset - Number of days offset from today (e.g., 0 = today, 1 = tomorrow, -7 = 7 days ago)
 * @returns Object with `start` and `end` Date objects in UTC
 */
export function getUKDateBoundaries(dayOffset: number = 0): { start: Date; end: Date } {
    const todayUk = getUkDatePartsForInstant(new Date())
    const targetUk = shiftYmd(todayUk, dayOffset)
    const nextUk = shiftYmd(targetUk, 1)

    const startUtc = getUkMidnightUtc(targetUk)
    const nextStartUtc = getUkMidnightUtc(nextUk)
    const endUtc = new Date(nextStartUtc.getTime() - 1)

    return { start: startUtc, end: endUtc }
}

/**
 * Get UK (Europe/London) date boundaries in UTC for a specific date string.
 * 
 * @param dateStr - Date string in "YYYY-MM-DD" format
 * @returns Object with `start` and `end` Date objects in UTC
 */
export function getUKDateBoundariesForDate(dateStr: string): { start: Date; end: Date } {
    const targetUk = parseYyyyMmDd(dateStr)
    const nextUk = shiftYmd(targetUk, 1)

    const startUtc = getUkMidnightUtc(targetUk)
    const nextStartUtc = getUkMidnightUtc(nextUk)
    const endUtc = new Date(nextStartUtc.getTime() - 1)

    return { start: startUtc, end: endUtc }
}
