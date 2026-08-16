"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, Activity, Flame, type LucideIcon } from "lucide-react"
import {
    PUBLIC_METER_DEVICE_ID,
    PUBLIC_TELEMETRY_SITE_ID,
    siteOrLegacyFilter,
} from "@/lib/telemetry-scope"

interface Reading {
    device_id: string
    channel: number
    power_w: number | null
    voltage: number | null
    energy_total_wh: number | null
    created_at: string
}

type ChannelStatus = "loading" | "online" | "stale" | "error" | "unavailable"

interface HeaterCardProps {
    name: string
    icon: LucideIcon
    power: number | null
    voltage: number | null
    energy: number | null
    isOn: boolean
    maxPower: number
    status: ChannelStatus
    readingAge: string
}

// Phase 1 records every channel once per minute. Allow several missed polls for
// transient cloud latency while still making a stopped collector visible.
const STALE_AFTER_MS = 5 * 60 * 1000

function getChannelStatus(
    reading: Reading | undefined,
    error: string | null,
    loading: boolean,
    nowMs: number,
): ChannelStatus {
    if (error) return "error"
    if (!reading) return loading ? "loading" : "unavailable"

    const timestamp = Date.parse(reading.created_at)
    if (!Number.isFinite(timestamp)) return "unavailable"

    const ageMs = nowMs - timestamp
    if (!(ageMs >= -60_000 && ageMs < STALE_AFTER_MS)) return "stale"

    // A fresh poll can deliberately retain an invalid source measurement as
    // NULL plus quality metadata. Freshness is not evidence of usable power.
    return typeof reading.power_w === "number" && Number.isFinite(reading.power_w)
        ? "online"
        : "unavailable"
}

function formatReadingAge(reading: Reading | undefined, nowMs: number) {
    if (!reading) return "No reading received"
    const timestamp = Date.parse(reading.created_at)
    if (!Number.isFinite(timestamp)) return "Reading time unavailable"

    const minutes = Math.max(0, Math.floor((nowMs - timestamp) / 60_000))
    if (minutes === 0) return "Updated just now"
    if (minutes === 1) return "Updated 1 min ago"
    return `Updated ${minutes} mins ago`
}

function ChannelStatusBadge({ status }: { status: ChannelStatus }) {
    if (status === "online") {
        return <Badge variant="secondary" className="text-xs">OFF</Badge>
    }
    if (status === "loading") {
        return <Badge variant="outline" className="text-xs">CHECKING</Badge>
    }
    if (status === "stale") {
        return <Badge variant="outline" className="border-amber-500 text-amber-600 text-xs">STALE</Badge>
    }
    if (status === "error") {
        return <Badge variant="destructive" className="text-xs">DATA ERROR</Badge>
    }
    return <Badge variant="destructive" className="text-xs">NO DATA</Badge>
}

// Both heaters are the same "hot water" thermal value stream, so they share
// one treatment: Live Signal marks an active/pulsing ON state, per brand spec.
function HeaterCard({ name, icon: Icon, power, voltage, energy, isOn, maxPower, status, readingAge }: HeaterCardProps) {
    const label = "text-[10px] font-mono uppercase tracking-[0.14em] text-muted-foreground"
    return (
        <Card className={`relative overflow-hidden transition-all duration-500 ${isOn ? "ring-2 ring-live shadow-lg shadow-live/20" : ""
            }`}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium">{name}</CardTitle>
                    {isOn ? (
                        <Badge className="bg-live text-live-foreground hover:bg-live/90 animate-pulse text-xs">
                            <Flame className="w-3 h-3 mr-1" />
                            ON
                        </Badge>
                    ) : <ChannelStatusBadge status={status} />}
                </div>
                <div className={`p-2 rounded-lg ${isOn ? "bg-live text-live-foreground" : "bg-secondary text-muted-foreground"}`}>
                    <Icon className="h-4 w-4" />
                </div>
            </CardHeader>

            <CardContent>
                <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-md bg-secondary/60 px-3 py-2">
                        <span className={`block ${label}`}>Power</span>
                        <span className="text-sm font-bold font-mono tabular-nums">
                            {power === null ? "—" : `${power.toFixed(0)}W`}
                        </span>
                    </div>
                    <div className="rounded-md bg-secondary/60 px-3 py-2">
                        <span className={`block ${label}`}>Voltage</span>
                        <span className="text-sm font-bold font-mono tabular-nums">
                            {voltage === null ? "—" : `${voltage.toFixed(1)}V`}
                        </span>
                    </div>
                    <div className="rounded-md bg-secondary/60 px-3 py-2">
                        <span className={`block ${label}`}>Total</span>
                        <span className="text-sm font-bold font-mono tabular-nums">
                            {energy === null ? "—" : `${(energy / 1000).toFixed(1)}kWh`}
                        </span>
                    </div>
                </div>

                <div className="mt-3 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all duration-500 ${isOn ? "bg-live" : "bg-muted-foreground/30"}`}
                        style={{ width: `${power === null ? 0 : Math.min((power / maxPower) * 100, 100)}%` }}
                    />
                </div>

                <p className="text-xs text-muted-foreground mt-2">{status === "error" ? "Latest telemetry request failed" : readingAge}</p>
            </CardContent>
        </Card>
    )
}

export function LiveStatus() {
    const [readings, setReadings] = useState<Partial<Record<0 | 1, Reading>>>({})
    const [loading, setLoading] = useState(true)
    const [errors, setErrors] = useState<Record<0 | 1, string | null>>({ 0: null, 1: null })
    const [nowMs, setNowMs] = useState(() => Date.now())

    useEffect(() => {
        let cancelled = false

        const fetchLive = async () => {
            try {
                const latestReadingQuery = (channel: 0 | 1) => {
                    let query = supabase
                        .from("energy_readings")
                        .select("*")
                        .eq("channel", channel)

                    if (PUBLIC_METER_DEVICE_ID && PUBLIC_TELEMETRY_SITE_ID) {
                        query = query.eq("device_id", PUBLIC_METER_DEVICE_ID)
                        query = query.or(siteOrLegacyFilter(PUBLIC_TELEMETRY_SITE_ID))
                    }

                    return query
                        .order("created_at", { ascending: false })
                        .limit(1)
                }

                const [channel0Response, channel1Response] = await Promise.all([
                    latestReadingQuery(0),
                    latestReadingQuery(1),
                ])

                if (cancelled) return

                setReadings((previous) => ({
                    0: channel0Response.error ? previous[0] : channel0Response.data?.[0],
                    1: channel1Response.error ? previous[1] : channel1Response.data?.[0],
                }))
                setErrors({
                    0: channel0Response.error?.message ?? null,
                    1: channel1Response.error?.message ?? null,
                })
            } catch (error) {
                if (cancelled) return
                const message = error instanceof Error ? error.message : "Telemetry request failed"
                setErrors({ 0: message, 1: message })
            } finally {
                if (!cancelled) {
                    setNowMs(Date.now())
                    setLoading(false)
                }
            }
        }

        void fetchLive()
        const pollInterval = window.setInterval(() => void fetchLive(), 30_000)
        const clockInterval = window.setInterval(() => setNowMs(Date.now()), 10_000)
        return () => {
            cancelled = true
            window.clearInterval(pollInterval)
            window.clearInterval(clockInterval)
        }
    }, [])

    const main = readings[0]
    const second = readings[1]
    const peakStatus = getChannelStatus(main, errors[0], loading, nowMs)
    const offPeakStatus = getChannelStatus(second, errors[1], loading, nowMs)
    const peakIsFresh = peakStatus === "online"
    const offPeakIsFresh = offPeakStatus === "online"
    const freshChannelCount = Number(peakIsFresh) + Number(offPeakIsFresh)

    // Determine if heaters are ON (power > 100W threshold)
    // Each channel must have its own fresh, successful reading.
    const isPeakOn = peakIsFresh && typeof main?.power_w === "number" && main.power_w > 100
    const isOffPeakOn = offPeakIsFresh && typeof second?.power_w === "number" && second.power_w > 100

    // Max power for progress bar (3kW heaters)
    const MAX_POWER = 3200

    return (
        <div className="space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <h2 className="font-display text-xl font-extrabold text-foreground">Heater Status (Live)</h2>
                <div className="flex items-center space-x-2 w-full sm:w-auto justify-between sm:justify-end">
                    <Badge
                        className={freshChannelCount === 2 ? "bg-live text-live-foreground hover:bg-live/90" : ""}
                        variant={freshChannelCount === 2 ? undefined : "destructive"}
                    >
                        <span className={`w-2 h-2 rounded-full mr-2 ${freshChannelCount === 2 ? "bg-live-foreground animate-pulse" : "bg-destructive-foreground/60"}`} />
                        {freshChannelCount}/2 channels fresh
                    </Badge>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
                <HeaterCard
                    name="Heater 1 (Boost)"
                    icon={Zap}
                    power={peakIsFresh ? (main?.power_w ?? null) : null}
                    voltage={peakIsFresh ? (main?.voltage ?? null) : null}
                    energy={peakIsFresh ? (main?.energy_total_wh ?? null) : null}
                    isOn={isPeakOn}
                    maxPower={MAX_POWER}
                    status={peakStatus}
                    readingAge={formatReadingAge(main, nowMs)}
                />
                <HeaterCard
                    name="Heater 2 (Storage)"
                    icon={Activity}
                    power={offPeakIsFresh ? (second?.power_w ?? null) : null}
                    voltage={offPeakIsFresh ? (second?.voltage ?? null) : null}
                    energy={offPeakIsFresh ? (second?.energy_total_wh ?? null) : null}
                    isOn={isOffPeakOn}
                    maxPower={MAX_POWER}
                    status={offPeakStatus}
                    readingAge={formatReadingAge(second, nowMs)}
                />
            </div>
        </div>
    )
}


