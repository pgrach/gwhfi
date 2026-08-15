import { Suspense } from "react"
import Link from "next/link"
import { LiveStatus } from "@/components/dashboard/LiveStatus"
import { CombinedHistoryChart } from "@/components/dashboard/CombinedHistoryChart"
import { CurrentRate } from "@/components/dashboard/CurrentRate"
import { PaidPriceInsights } from "@/components/dashboard/PaidPriceInsights"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { Zap, Droplet, ArrowLeft } from "lucide-react"

export const dynamic = 'force-dynamic'

export default function DashboardPage() {
    return (
        <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between space-y-2 md:space-y-0">
                <Link
                    href="/"
                    className="group flex items-center gap-4 rounded-lg -m-2 p-2 transition-colors hover:bg-accent"
                >
                    <div className="relative flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 text-white shadow-lg shadow-blue-500/25 shrink-0">
                        <Zap className="w-7 h-7 absolute z-10 fill-white" />
                        <Droplet className="w-9 h-9 opacity-20 fill-white" />
                    </div>
                    <div>
                        <h2 className="text-2xl md:text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-cyan-500">
                            SmartWater
                        </h2>
                        <p className="text-sm text-muted-foreground font-medium flex items-center gap-1">
                            <ArrowLeft className="w-3.5 h-3.5 opacity-0 -ml-4 transition-all group-hover:opacity-100 group-hover:ml-0" />
                            Intelligent Heating Dashboard
                        </p>
                    </div>
                </Link>
                <ThemeToggle />
            </div>
            <div className="space-y-5">
                <Suspense fallback={<div className="text-muted-foreground">Loading insights...</div>}>
                    <PaidPriceInsights />
                </Suspense>

                <div className="space-y-4">
                    <h3 className="text-lg font-semibold">Live Operations</h3>
                    <CurrentRate />
                    <LiveStatus />
                </div>

                <div className="space-y-3">
                    <h3 className="text-lg font-semibold">Usage & Price Trend</h3>
                    <Suspense fallback={<div className="h-[400px] flex items-center justify-center text-muted-foreground">Loading chart...</div>}>
                        <CombinedHistoryChart />
                    </Suspense>
                </div>
            </div>
        </div>
    )
}
