"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine
} from "recharts"

interface Rate {
    value_inc_vat: number
    valid_from: string
    valid_to: string
}

export function RatesChart() {
    const [rates, setRates] = useState<any[]>([])
    const [viewDate, setViewDate] = useState<"today" | "tomorrow">("today")
    const [loading, setLoading] = useState(true)

    // Configuration - Ideally this comes from Env Vars but these are safe public defaults for Agile
    const PRODUCT = "AGILE-18-02-21"
    const REGION = "C" // London
    const TARIFF = `E-1R-${PRODUCT}-${REGION}`

    useEffect(() => {
        const fetchRates = async () => {
            setLoading(true)
            try {
                // Fetch rates for a wide range (last 2 days to next 2 days to be safe)
                // The API pagination handles 100 items per page usually.
                // We'll just fetch the 'standard-unit-rates' endpoint which returns paginated recent rates.
                // Or we can filter by period_from if we want to be specific, but getting the default list is often easiest for "latest".

                const response = await fetch(
                    `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/`
                )
                const data = await response.json()

                if (data.results) {
                    processRates(data.results)
                }
            } catch (error) {
                console.error("Failed to fetch rates:", error)
            }
            setLoading(false)
        }

        fetchRates()
    }, [])

    const processRates = (apiRates: Rate[]) => {
        // Filter and sort
        // We want to group by "Today" and "Tomorrow"
        // API returns ISO strings.

        const now = new Date()
        const todayStr = now.toISOString().split("T")[0]

        const tomorrow = new Date(now)
        tomorrow.setDate(tomorrow.getDate() + 1)
        const tomorrowStr = tomorrow.toISOString().split("T")[0]

        // Create a map for chart data
        // We want to show 00:00 to 23:30 for the selected day.

        // Helper to get day string
        const getDayStr = (iso: string) => iso.split("T")[0]

        const todayRates = apiRates
            .filter(r => getDayStr(r.valid_from) === todayStr)
            .sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())

        const tomorrowRates = apiRates
            .filter(r => getDayStr(r.valid_from) === tomorrowStr)
            .sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())

        // Map to chart format
        const formatData = (rawConfig: Rate[]) => rawConfig.map(r => ({
            time: new Date(r.valid_from).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            price: r.value_inc_vat,
            negative: r.value_inc_vat < 0 ? r.value_inc_vat : 0
        }))

        // Store entire set, toggle view in render? No, let's store processed sets.
        // Actually, let's just keep the whole list and filter in render or effect dependancy.
        // For simplicity, let's store the raw 'results' in a ref or state and process on viewDate change?
        // Let's just setState with the raw list for now to avoid complexity in this snippet

        // Actually, let's save the 'display data' in state
        if (viewDate === "today") setRates(formatData(todayRates))
        else setRates(formatData(tomorrowRates))

        // We need to re-run this when viewDate changes. 
        // So we need to store 'allRates' separately.
    }

    // Refactored for proper state management
    const [allRates, setAllRates] = useState<Rate[]>([])

    useEffect(() => {
        const fetchRates = async () => {
            try {
                // Fetch generous amount to cover tomorrow
                const response = await fetch(
                    `https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?page_size=100`
                )
                // Note: default page size is 100, which is ~48 hours (30 min slots = 48 per day). 
                // So 100 covers today and tomorrow mostly.

                const data = await response.json()
                if (data.results) {
                    setAllRates(data.results)
                }
            } catch (e) { console.error(e) }
        }
        fetchRates()
    }, [])

    useEffect(() => {
        if (allRates.length === 0) return

        const targetDate = new Date()
        if (viewDate === "tomorrow") {
            targetDate.setDate(targetDate.getDate() + 1)
        }
        const targetStr = targetDate.toISOString().split("T")[0]

        const getDayStr = (iso: string) => iso.split("T")[0]

        const filtered = allRates
            .filter(r => getDayStr(r.valid_from) === targetStr)
            .sort((a, b) => new Date(a.valid_from).getTime() - new Date(b.valid_from).getTime())
            .map(r => ({
                time: new Date(r.valid_from).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                price: r.value_inc_vat
            }))

        setRates(filtered)
    }, [viewDate, allRates])


    return (
        <Card className="col-span-4">
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Octopus Agile Rates ({viewDate === "today" ? "Today" : "Tomorrow"})</CardTitle>
                <div className="flex space-x-2">
                    <Button
                        variant={viewDate === "today" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setViewDate("today")}
                    >
                        Today
                    </Button>
                    <Button
                        variant={viewDate === "tomorrow" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setViewDate("tomorrow")}
                    >
                        Tomorrow
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="pl-2">
                <div className="h-[300px] w-full">
                    {rates.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={rates}>
                                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                                <XAxis
                                    dataKey="time"
                                    stroke="#888888"
                                    fontSize={12}
                                    tickLine={false}
                                    axisLine={false}
                                    minTickGap={30}
                                />
                                <YAxis
                                    stroke="#888888"
                                    fontSize={12}
                                    tickLine={false}
                                    axisLine={false}
                                    tickFormatter={(value) => `${value}p`}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: "#1f2937", border: "none", color: "#fff" }}
                                    formatter={(value: any) => [`${Number(value).toFixed(2)}p`, "Price"]}
                                />
                                <ReferenceLine y={0} stroke="green" strokeDasharray="3 3" />
                                <Line
                                    type="stepAfter"
                                    dataKey="price"
                                    stroke="#8884d8"
                                    strokeWidth={2}
                                    dot={false}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="flex h-full items-center justify-center text-muted-foreground">
                            {viewDate === "tomorrow" ? "Rates not yet available for tomorrow." : "Loading rates..."}
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    )
}
