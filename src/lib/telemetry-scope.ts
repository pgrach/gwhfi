// Keep device scoping consistent across browser and server queries.
export function normalizeMeterDeviceId(value: string | null | undefined): string | null {
    const normalized = value?.trim()
    return normalized ? normalized : null
}

export function resolveMeterDeviceId(...values: Array<string | null | undefined>): string | null {
    for (const value of values) {
        const normalized = normalizeMeterDeviceId(value)
        if (normalized) return normalized
    }
    return null
}

export function siteOrLegacyFilter(siteId: string): string {
    // Deployment-controlled site IDs are simple slugs. Reject syntax that
    // could change the raw PostgREST `or` expression rather than broadening it.
    if (!/^[A-Za-z0-9._:-]+$/.test(siteId)) {
        throw new Error("Telemetry site ID must be a simple slug")
    }
    return `site_id.eq.${siteId},site_id.is.null`
}

export const PUBLIC_METER_DEVICE_ID = normalizeMeterDeviceId(
    process.env.NEXT_PUBLIC_SHELLY_METER_DEVICE_ID,
)
export const PUBLIC_TELEMETRY_SITE_ID = normalizeMeterDeviceId(
    process.env.NEXT_PUBLIC_TELEMETRY_SITE_ID,
)

interface DownsampledReadingsRequest {
    functionName: "get_downsampled_readings" | "get_downsampled_readings_for_device"
    params: {
        start_time: string
        end_time: string
        bucket_seconds: number
        target_device_id?: string
        target_site_id?: string
    }
}

interface EnergyCounterSeriesRequest {
    functionName: "get_energy_counter_series_for_device"
    params: {
        start_time: string
        end_time: string
        bucket_seconds: number
        target_site_id: string
        target_device_id: string
    }
}

export function buildDownsampledReadingsRequest(
    startTime: string,
    endTime: string,
    bucketSeconds: number,
    meterDeviceId: string | null,
    siteId: string | null,
): DownsampledReadingsRequest {
    if (meterDeviceId && siteId) {
        return {
            functionName: "get_downsampled_readings_for_device",
            params: {
                start_time: startTime,
                end_time: endTime,
                bucket_seconds: bucketSeconds,
                target_device_id: meterDeviceId,
                target_site_id: siteId,
            },
        }
    }

    return {
        functionName: "get_downsampled_readings",
        params: {
            start_time: startTime,
            end_time: endTime,
            bucket_seconds: bucketSeconds,
        },
    }
}

export function buildEnergyCounterSeriesRequest(
    startTime: string,
    endTime: string,
    bucketSeconds: number,
    siteId: string | null,
    meterDeviceId: string | null,
): EnergyCounterSeriesRequest {
    if (!siteId || !meterDeviceId) {
        throw new Error("Counter series requires both telemetry site and meter IDs")
    }

    return {
        functionName: "get_energy_counter_series_for_device",
        params: {
            start_time: startTime,
            end_time: endTime,
            bucket_seconds: bucketSeconds,
            target_site_id: siteId,
            target_device_id: meterDeviceId,
        },
    }
}
