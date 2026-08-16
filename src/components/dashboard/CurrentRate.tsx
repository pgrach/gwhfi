"use client"

import { useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, Sparkles, Check, Clock } from "lucide-react"
import { supabase } from "@/lib/supabase"
import { getUKDateBoundaries } from "@/lib/date-utils"
import { OCTOPUS_RATES_URL } from "@/lib/octopus-config"

interface Rate {
    value_inc_vat: number
    valid_from: string
    valid_to: string
}

export function CurrentRate() {
    const [currentRate, setCurrentRate] = useState<Rate | null>(null)
    const [avgRate, setAvgRate] = useState<number>(0)
    const [nextSmartSlot, setNextSmartSlot] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchRates = async () => {
            try {
                const now = new Date()
                const { start: startOfDay, end: endOfDay } = getUKDateBoundaries(0)

                const [response, scheduleResponse] = await Promise.all([
                    fetch(
                        `${OCTOPUS_RATES_URL}?period_from=${startOfDay.toISOString()}&period_to=${endOfDay.toISOString()}`
                    ),
                    supabase
                        .from('heating_schedule')
                        .select('*')
                        .eq('heater_type', 'off_peak')
                        .gt('slot_start', now.toISOString())
                        .order('slot_start', { ascending: true })
                        .limit(1)
                ])

                const data = await response.json()
                const rates: Rate[] = data.results || []

                const scheduleData = scheduleResponse.data

                if (rates.length === 0) {
                    setLoading(false)
                    return
                }

                // Calculate daily average
                const sum = rates.reduce((a, b) => a + b.value_inc_vat, 0)
                const avg = sum / rates.length
                setAvgRate(avg)

                // Find current rate
                const nowTime = now.getTime()
                const current = rates.find(r => {
                    const from = new Date(r.valid_from).getTime()
                    const to = new Date(r.valid_to).getTime()
                    return nowTime >= from && nowTime < to
                })
                setCurrentRate(current || null)

                // Find next smart slot (from schedule)
                if (scheduleData && scheduleData.length > 0) {
                    const nextSlot = scheduleData[0]
                    const nextTime = new Date(nextSlot.slot_start)
                    const diffMs = nextTime.getTime() - nowTime

                    const hours = Math.floor(diffMs / (1000 * 60 * 60))
                    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))

                    const timeStr = nextTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    const durationStr = `in ${hours}h ${minutes}m`

                    setNextSmartSlot(`${timeStr} (${durationStr})`)
                } else {
                    setNextSmartSlot("None scheduled")
                }

                setLoading(false)
            } catch (error) {
                console.error("Failed to fetch rates:", error)
                setLoading(false)
            }
        }

        fetchRates()
        // Refresh every 5 minutes
        const interval = setInterval(fetchRates, 5 * 60 * 1000)
        return () => clearInterval(interval)
    }, [])

    if (loading) {
        return (
            <Card>
                <CardContent className="p-4">
                    <div className="animate-pulse flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-rust/10"></div>
                        <div className="space-y-2 flex-1">
                            <div className="h-4 bg-muted rounded w-1/3"></div>
                            <div className="h-6 bg-muted rounded w-1/2"></div>
                        </div>
                    </div>
                </CardContent>
            </Card>
        )
    }

    const isSmart = currentRate && currentRate.value_inc_vat <= avgRate
    const isNegative = currentRate && currentRate.value_inc_vat <= 0
    const eyebrow = "text-[10px] font-mono font-medium uppercase tracking-[0.14em] text-muted-foreground"

    // Rust is the single signal accent — used here for the rate figure and
    // its icon, sparingly (icon chip only, never a full-card fill).
    return (
        <Card className={isNegative ? "border-live/40 shadow-lg shadow-live/10" : ""}>
            <CardContent className="p-4">
                <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                    {/* Current Rate */}
                    <div className="flex items-center gap-4 flex-1">
                        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-rust/10">
                            <Zap className="w-6 h-6 text-rust" />
                        </div>
                        <div>
                            <p className={eyebrow}>Live Electricity Rate</p>
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-2xl font-bold font-mono tabular-nums text-rust">
                                    {currentRate ? currentRate.value_inc_vat.toFixed(2) : "—"}p/kWh
                                </span>
                                {isNegative && (
                                    <Badge className="bg-live text-live-foreground hover:bg-live/90 animate-pulse">
                                        <Sparkles className="w-3 h-3" />
                                        You&apos;re earning
                                    </Badge>
                                )}
                                {isSmart && !isNegative && (
                                    <Badge variant="outline" className="border-rust/30 bg-rust/10 text-rust">
                                        <Check className="w-3 h-3" />
                                        Below Avg
                                    </Badge>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Divider */}
                    <div className="hidden lg:block w-px h-12 bg-border"></div>

                    {/* Daily Average */}
                    <div className="flex items-center gap-4">
                        <div className="text-left">
                            <p className={eyebrow}>Agile Daily Average</p>
                            <span className="text-lg font-semibold font-mono tabular-nums">{avgRate.toFixed(2)}p/kWh</span>
                        </div>
                    </div>

                    {/* Divider */}
                    <div className="hidden lg:block w-px h-12 bg-border"></div>

                    {/* Next Smart Slot */}
                    <div className="flex items-center gap-3">
                        <Clock className="w-5 h-5 text-muted-foreground" />
                        <div>
                            <p className={eyebrow}>Next Scheduled Heating</p>
                            <span className="text-lg font-semibold whitespace-nowrap">
                                {nextSmartSlot || "—"}
                            </span>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
