import { LiveStatus } from "@/components/dashboard/LiveStatus"
import { CombinedHistoryChart } from "@/components/dashboard/CombinedHistoryChart"
import { Zap, Droplet } from "lucide-react"

export default function DashboardPage() {
    return (
        <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between space-y-2 md:space-y-0">
                <div className="flex items-center gap-4">
                    <div className="relative flex items-center justify-center w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 text-white shadow-lg shadow-blue-500/25 shrink-0">
                        <Zap className="w-7 h-7 absolute z-10 fill-white" />
                        <Droplet className="w-9 h-9 opacity-20 fill-white" />
                    </div>
                    <div>
                        <h2 className="text-2xl md:text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-cyan-500">
                            SmartWater
                        </h2>
                        <p className="text-sm text-muted-foreground font-medium">
                            Intelligent Heating Dashboard
                        </p>
                    </div>
                </div>
            </div>
            <div className="space-y-4">
                <LiveStatus />
                <CombinedHistoryChart />
            </div>
        </div>
    )
}
