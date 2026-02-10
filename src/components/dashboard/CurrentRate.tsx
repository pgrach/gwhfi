"use client"

import { useEffect, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, TrendingDown, Clock } from "lucide-react"
import { supabase } from "@/lib/supabase"
import { getUKDateBoundaries } from "@/lib/date-utils"

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

    const PRODUCT = "AGILE-24-10-01"
    const REGION = "C"
    const TARIFF = `E-1R-${PRODUCT}-${REGION}`

    useEffect(() => {
        const fetchRates = async () => {
            try {
                const now = new Date()
                const { start: startOfDay, end: endOfDay } = getUKDateBoundaries(0)

                // Fetch Rates
                const response = await fetch(
                    `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?period_from=${startOfDay.toISOString()}&period_to=${endOfDay.toISOString()}`
                )
                const data = await response.json()
                const rates: Rate[] = data.results || []

                // Fetch Schedule
                const { data: scheduleData, error: scheduleError } = await supabase
                    .from('heating_schedule')
                    .select('*')
                    .gt('slot_start', now.toISOString())
                    .order('slot_start', { ascending: true })
                    .limit(1)

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
            <Card className="bg-gradient-to-br from-purple-500/10 to-pink-500/10 border-purple-500/20">
                <CardContent className="p-4">
                    <div className="animate-pulse flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-purple-500/20"></div>
                        <div className="space-y-2 flex-1">
                            <div className="h-4 bg-purple-500/20 rounded w-1/3"></div>
                            <div className="h-6 bg-purple-500/20 rounded w-1/2"></div>
                        </div>
                    </div>
                </CardContent>
            </Card>
        )
    }

    const isSmart = currentRate && currentRate.value_inc_vat <= avgRate
    const isNegative = currentRate && currentRate.value_inc_vat <= 0

    return (
        <Card className={`transition-all duration-300 ${isNegative
            ? "bg-gradient-to-br from-green-500/20 to-emerald-500/20 border-green-500/40 shadow-lg shadow-green-500/10"
            : isSmart
                ? "bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border-emerald-500/20"
                : "bg-gradient-to-br from-purple-500/10 to-pink-500/10 border-purple-500/20"
            }`}>
            <CardContent className="p-4">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    {/* Current Rate */}
                    <div className="flex items-center gap-4 flex-1">
                        <div className={`flex items-center justify-center w-12 h-12 rounded-xl ${isNegative
                            ? "bg-green-500 shadow-lg shadow-green-500/30"
                            : isSmart
                                ? "bg-emerald-500"
                                : "bg-purple-500"
                            }`}>
                            {isNegative ? (
                                <TrendingDown className="w-6 h-6 text-white" />
                            ) : (
                                <Zap className="w-6 h-6 text-white" />
                            )}
                        </div>
                        <div>
                            <p className="text-sm text-muted-foreground font-medium">Current Rate</p>
                            <div className="flex items-center gap-2">
                                <span className={`text-2xl font-bold ${isNegative ? "text-green-500" : isSmart ? "text-emerald-500" : ""
                                    }`}>
                                    {currentRate ? currentRate.value_inc_vat.toFixed(2) : "—"}p/kWh
                                </span>
                                {isNegative && (
                                    <Badge className="bg-green-500 hover:bg-green-600 animate-pulse">
                                        💰 NEGATIVE
                                    </Badge>
                                )}
                                {isSmart && !isNegative && (
                                    <Badge className="bg-emerald-500 hover:bg-emerald-600">
                                        ✓ Below Avg
                                    </Badge>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Divider */}
                    <div className="hidden sm:block w-px h-12 bg-border"></div>

                    {/* Daily Average */}
                    <div className="flex items-center gap-4">
                        <div className="text-center sm:text-left">
                            <p className="text-sm text-muted-foreground font-medium">Daily Average</p>
                            <span className="text-lg font-semibold">{avgRate.toFixed(2)}p/kWh</span>
                        </div>
                    </div>

                    {/* Divider */}
                    <div className="hidden sm:block w-px h-12 bg-border"></div>

                    {/* Next Smart Slot */}
                    <div className="flex items-center gap-3">
                        <Clock className="w-5 h-5 text-muted-foreground" />
                        <div>
                            <p className="text-sm text-muted-foreground font-medium">Next Smart Slot</p>
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
