import { Suspense } from "react"
import Link from "next/link"
import { LiveStatus } from "@/components/dashboard/LiveStatus"
import { CombinedHistoryChart } from "@/components/dashboard/CombinedHistoryChart"
import { CurrentRate } from "@/components/dashboard/CurrentRate"
import { PaidPriceInsights } from "@/components/dashboard/PaidPriceInsights"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { Heat21Mark } from "@/components/ui/heat21-mark"
import { ArrowLeft } from "lucide-react"

export const dynamic = 'force-dynamic'

export default function DashboardPage() {
    return (
        <div className="flex-1 space-y-8 p-4 md:p-8 pt-6 mx-auto max-w-7xl">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-2">
                <Link
                    href="/"
                    className="group flex items-center gap-3 rounded-lg -m-2 p-2 transition-colors hover:bg-accent"
                >
                    <Heat21Mark className="h-7 w-auto text-rust shrink-0" />
                    <div>
                        <h2 className="font-display text-2xl md:text-3xl font-extrabold tracking-tight text-foreground">
                            Heat21
                        </h2>
                        <p className="text-[10px] font-mono font-medium uppercase tracking-[0.18em] text-muted-foreground flex items-center gap-1.5">
                            <ArrowLeft className="w-3 h-3 opacity-0 -ml-4 transition-all group-hover:opacity-100 group-hover:ml-0" />
                            Smarter Electric Heat
                        </p>
                    </div>
                </Link>
                <ThemeToggle />
            </div>
            <div className="space-y-8">
                <Suspense fallback={<div className="text-muted-foreground">Loading insights...</div>}>
                    <PaidPriceInsights />
                </Suspense>

                <div className="space-y-4">
                    <h3 className="font-display text-xl font-extrabold text-foreground">Live Operations</h3>
                    <CurrentRate />
                    <LiveStatus />
                </div>

                <div className="space-y-3">
                    <h3 className="font-display text-xl font-extrabold text-foreground">Usage & Price Trend</h3>
                    <Suspense fallback={<div className="h-[400px] flex items-center justify-center text-muted-foreground">Loading chart...</div>}>
                        <CombinedHistoryChart />
                    </Suspense>
                </div>
            </div>
        </div>
    )
}
