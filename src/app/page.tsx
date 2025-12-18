import { LiveStatus } from "@/components/dashboard/LiveStatus"
import { HistoryChart } from "@/components/dashboard/HistoryChart"

export default function DashboardPage() {
    return (
        <div className="flex-1 space-y-4 p-8 pt-6">
            <div className="flex items-center justify-between space-y-2">
                <h2 className="text-3xl font-bold tracking-tight">💧 Smart Water Dashboard</h2>
            </div>
            <div className="space-y-4">
                <LiveStatus />
                <HistoryChart />
            </div>
        </div>
    )
}
