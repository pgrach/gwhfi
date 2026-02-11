import { Activity, Wifi, WifiOff, Thermometer, Zap, BarChart3, ExternalLink } from "lucide-react";

export function DashboardPreviewSection() {
  return (
    <section
      id="dashboard"
      className="border-t border-border px-6 py-24 md:py-32"
    >
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          Live Dashboard
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          See it in action
        </h2>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground text-pretty">
          Every GWhFi unit reports real-time telemetry to the SmartWater
          Dashboard. Monitor heater status, power draw, energy consumption,
          and thermal output from anywhere.
        </p>

        {/* Dashboard mockup */}
        <div className="mt-16 overflow-hidden rounded-lg border border-border">
          {/* Title bar */}
          <div className="flex items-center justify-between border-b border-border bg-card px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-full bg-muted-foreground/30" />
                <span className="h-3 w-3 rounded-full bg-muted-foreground/30" />
                <span className="h-3 w-3 rounded-full bg-muted-foreground/30" />
              </div>
              <span className="ml-2 text-xs text-muted-foreground">
                gwhfi.com
              </span>
            </div>
            <a
              href="https://www.gwhfi.com/dashboard"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs font-medium text-primary transition-colors hover:text-primary/80"
            >
              Open live
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>

          {/* Dashboard content */}
          <div className="bg-[hsl(213,30%,12%)] p-6 md:p-8">
            {/* Header */}
            <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-serif text-lg font-bold text-foreground">
                  SmartWater Dashboard
                </h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Intelligent Heating Dashboard
                </p>
              </div>
              <div className="flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1.5">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
                </span>
                <span className="text-xs font-medium text-primary">
                  Live Status
                </span>
              </div>
            </div>

            {/* Heater cards */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {/* Heater 1 */}
              <div className="rounded-lg border border-border bg-card p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
                      <Thermometer className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <span className="text-sm font-semibold text-foreground">
                        Heater 1
                      </span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        (Boost)
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Wifi className="h-3.5 w-3.5 text-primary" />
                    <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                      ON
                    </span>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3">
                  <div className="rounded-md bg-secondary px-3 py-2">
                    <span className="block text-xs text-muted-foreground">
                      Power
                    </span>
                    <span className="text-sm font-bold text-foreground">
                      3,012W
                    </span>
                  </div>
                  <div className="rounded-md bg-secondary px-3 py-2">
                    <span className="block text-xs text-muted-foreground">
                      Voltage
                    </span>
                    <span className="text-sm font-bold text-foreground">
                      242.1V
                    </span>
                  </div>
                  <div className="rounded-md bg-secondary px-3 py-2">
                    <span className="block text-xs text-muted-foreground">
                      Total
                    </span>
                    <span className="text-sm font-bold text-foreground">
                      127.4 kWh
                    </span>
                  </div>
                </div>
              </div>

              {/* Heater 2 */}
              <div className="rounded-lg border border-border bg-card p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                      <Thermometer className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <span className="text-sm font-semibold text-foreground">
                        Heater 2
                      </span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        (Storage)
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <WifiOff className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                      OFF
                    </span>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3">
                  <div className="rounded-md bg-secondary px-3 py-2">
                    <span className="block text-xs text-muted-foreground">
                      Power
                    </span>
                    <span className="text-sm font-bold text-muted-foreground">
                      0W
                    </span>
                  </div>
                  <div className="rounded-md bg-secondary px-3 py-2">
                    <span className="block text-xs text-muted-foreground">
                      Voltage
                    </span>
                    <span className="text-sm font-bold text-muted-foreground">
                      0.0V
                    </span>
                  </div>
                  <div className="rounded-md bg-secondary px-3 py-2">
                    <span className="block text-xs text-muted-foreground">
                      Total
                    </span>
                    <span className="text-sm font-bold text-foreground">
                      84.2 kWh
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Chart area placeholder */}
            <div className="mt-4 rounded-lg border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-foreground">
                    Combined History
                  </span>
                </div>
                <div className="flex gap-1">
                  {["Today", "7d", "30d"].map((label, i) => (
                    <span
                      key={label}
                      className={`rounded-md px-2.5 py-1 text-xs font-medium ${i === 0
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground"
                        }`}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>

              {/* Stylised chart bars */}
              <div className="flex items-end gap-1.5 h-24">
                {[35, 52, 68, 45, 78, 90, 62, 85, 73, 55, 92, 40, 65, 80, 48, 70, 88, 56, 42, 75, 60, 83, 50, 38].map(
                  (h, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-sm bg-primary/30"
                      style={{ height: `${h}%` }}
                    />
                  )
                )}
              </div>

              <div className="mt-4 flex gap-6">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    Peak:
                  </span>
                  <span className="text-xs font-semibold text-foreground">
                    18.42 kWh
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    Off-Peak:
                  </span>
                  <span className="text-xs font-semibold text-foreground">
                    24.67 kWh
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* CTA below the dashboard preview */}
        <div className="mt-8 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
          <a
            href="https://www.gwhfi.com/dashboard"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-8 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Activity className="h-4 w-4" />
            Open Live Dashboard
          </a>
          <span className="text-xs text-muted-foreground">
            Real-time heater telemetry from a live GWhFi unit
          </span>
        </div>
      </div>
    </section>
  );
}
