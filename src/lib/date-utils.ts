/**
 * UK Date Boundary Utilities
 * 
 * Handles timezone-aware date boundary calculations for Europe/London,
 * correctly accounting for GMT/BST transitions.
 */

/**
 * Get UK (Europe/London) date boundaries in UTC.
 * Ensures "today" always means UK midnight-to-midnight regardless of viewer's timezone.
 * 
 * @param dayOffset - Number of days offset from today (e.g., 0 = today, 1 = tomorrow, -7 = 7 days ago)
 * @returns Object with `start` and `end` Date objects in UTC
 */
export function getUKDateBoundaries(dayOffset: number = 0): { start: Date; end: Date } {
    const now = new Date()
    const ukFormatter = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Europe/London',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    })
    const parts = ukFormatter.formatToParts(now)
    const year = parseInt(parts.find(p => p.type === 'year')!.value)
    const month = parseInt(parts.find(p => p.type === 'month')!.value)
    const day = parseInt(parts.find(p => p.type === 'day')!.value)

    // Build a UTC date and find the offset for UK timezone at that date
    const tempDate = new Date(Date.UTC(year, month - 1, day + dayOffset, 0, 0, 0))
    const ukTimeStr = tempDate.toLocaleString('en-US', { timeZone: 'Europe/London' })
    const ukTime = new Date(ukTimeStr)
    const offsetMs = ukTime.getTime() - tempDate.getTime()

    // UK midnight in UTC = midnight minus the offset (handles BST/GMT automatically)
    const startUtc = new Date(tempDate.getTime() - offsetMs)
    const endUtc = new Date(startUtc.getTime() + 24 * 60 * 60 * 1000 - 1) // 23:59:59.999

    return { start: startUtc, end: endUtc }
}
