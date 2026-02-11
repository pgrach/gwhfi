"use client";

import { useEffect, useState } from "react";
import {
  Wind,
  XCircle,
  ArrowRight,
  CheckCircle,
  ExternalLink,
  Bitcoin,
} from "lucide-react";

interface CurtailmentData {
  today: {
    energy_gwh: number;
    energy_mwh: number;
    payment: number;
    btc: number;
    btc_value_gbp: number | null;
  };
  date: string;
  source: string;
}

function formatNumber(n: number): string {
  return n.toLocaleString("en-GB");
}

function LiveBadge() {
  return (
    <a
      href="https://curtailcoin.com"
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20"
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-destructive opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-destructive" />
      </span>
      Live from CurtailCoin
      <ExternalLink className="h-3 w-3" />
    </a>
  );
}

function StatSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      <div className="h-8 w-20 rounded bg-muted" />
      <div className="h-4 w-28 rounded bg-muted" />
    </div>
  );
}

export function ProblemSection() {
  const [data, setData] = useState<CurtailmentData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/curtailment")
      .then((res) => (res.ok ? res.json() : null))
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section id="problem" className="px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          The Problem
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          The UK wastes billions in clean energy every year
        </h2>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground text-pretty">
          When renewable generation exceeds grid demand, operators pay wind and
          solar farms to stop producing. This curtailment cost UK bill-payers
          {"\u00A0"}£1.46 billion in 2023 alone, wasting 4.6 TWh of clean
          electricity.
        </p>

        {/* Before / After diagram */}
        <div className="mt-16 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* ── LEFT: Today – Energy Wasted ── */}
          <div className="rounded-lg border border-border bg-card p-8">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
                  <XCircle className="h-5 w-5 text-destructive" />
                </div>
                <h3 className="font-serif text-xl font-semibold text-foreground">
                  Today: Energy Wasted
                </h3>
              </div>
              {data && <LiveBadge />}
            </div>

            {/* Live stats: energy + cost */}
            {(loading || data) && (
              <div className="mb-6 grid grid-cols-2 gap-4 rounded-md border border-border bg-secondary/50 p-4">
                {loading ? (
                  <>
                    <StatSkeleton />
                    <StatSkeleton />
                  </>
                ) : data ? (
                  <>
                    <div>
                      <span className="block font-serif text-2xl font-bold text-destructive">
                        {data.today.energy_gwh} GWh
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Curtailed today
                      </span>
                    </div>
                    <div>
                      <span className="block font-serif text-2xl font-bold text-foreground">
                        £{formatNumber(data.today.payment)}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Cost to consumers
                      </span>
                    </div>
                  </>
                ) : null}
              </div>
            )}

            <div className="flex flex-col gap-4">
              {/* Flow diagram */}
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-border bg-secondary">
                  <Wind className="h-6 w-6 text-muted-foreground" />
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="flex-1 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
                  <span className="text-sm font-medium text-foreground">
                    Grid at capacity
                  </span>
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="flex-1 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
                  <span className="text-sm font-medium text-destructive">
                    Curtailed
                  </span>
                </div>
              </div>

              <div className="mt-4 space-y-3 text-sm text-muted-foreground">
                <div className="flex items-start gap-2">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive/70" />
                  <span>Wind farms paid to switch off</span>
                </div>
                <div className="flex items-start gap-2">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive/70" />
                  <span>£1.46B in constraint payments added to bills</span>
                </div>
                <div className="flex items-start gap-2">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive/70" />
                  <span>Clean energy goes to waste</span>
                </div>
              </div>

              {data && (
                <a
                  href="https://curtailcoin.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-primary"
                >
                  See full breakdown on CurtailCoin →
                </a>
              )}
            </div>
          </div>

          {/* ── RIGHT: With GWhFi – Energy Used ── */}
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-8">
            <div className="mb-6 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <CheckCircle className="h-5 w-5 text-primary" />
              </div>
              <h3 className="font-serif text-xl font-semibold text-foreground">
                With GWhFi: Energy Used
              </h3>
            </div>

            {/* Live stats: BTC potential */}
            {(loading || data) && (
              <div className="mb-6 grid grid-cols-2 gap-4 rounded-md border border-primary/20 bg-primary/5 p-4">
                {loading ? (
                  <>
                    <StatSkeleton />
                    <StatSkeleton />
                  </>
                ) : data ? (
                  <>
                    <div className="flex items-start gap-2">
                      <Bitcoin className="mt-1 h-5 w-5 shrink-0 text-primary" />
                      <div>
                        <span className="block font-serif text-2xl font-bold text-primary">
                          {data.today.btc} BTC
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Could have mined today
                        </span>
                      </div>
                    </div>
                    <div>
                      <span className="block font-serif text-2xl font-bold text-primary">
                        {data.today.btc_value_gbp
                          ? `£${formatNumber(data.today.btc_value_gbp)}`
                          : "—"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Value in GBP
                      </span>
                    </div>
                  </>
                ) : null}
              </div>
            )}

            <div className="flex flex-col gap-4">
              {/* Flow diagram */}
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/10">
                  <Wind className="h-6 w-6 text-primary" />
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-primary" />
                <div className="flex-1 rounded-md border border-primary/30 bg-primary/10 px-4 py-3">
                  <span className="text-sm font-medium text-foreground">
                    ASIC Heater
                  </span>
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-primary" />
                <div className="flex-1 rounded-md border border-primary/30 bg-primary/10 px-4 py-3">
                  <span className="text-sm font-medium text-primary">
                    3 value streams
                  </span>
                </div>
              </div>

              <div className="mt-4 space-y-3 text-sm text-muted-foreground">
                <div className="flex items-start gap-2">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>Surplus energy heats domestic hot water</span>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>Bitcoin mining generates additional revenue</span>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>Grid flexibility payments reduce system costs</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
