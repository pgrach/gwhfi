"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";

interface CurtailmentData {
  month: {
    energy_gwh: number;
    payment: number;
  };
}

const staticCards = [
  {
    value: "£1.46B",
    label: "Constraint costs",
    context: "Paid by UK bill-payers annually",
  },
  {
    value: "27 GW",
    label: "Installed wind capacity",
    context: "And growing by 3 GW per year",
  },
  {
    value: "23M",
    label: "UK hot water cylinders",
    context: "Each one a potential thermal store",
  },
  {
    value: "2 kW",
    label: "Per-unit power draw",
    context: "Standard domestic immersion rating",
  },
  {
    value: "£180M+",
    label: "Annual flex market value",
    context: "Growing as renewables increase",
  },
];

function LiveCard({ data }: { data: CurtailmentData | null; loading: boolean }) {
  if (!data) {
    // Fallback to static card
    return (
      <div className="flex flex-col bg-card px-6 py-8">
        <span className="font-serif text-3xl font-bold text-primary">
          4.6 TWh
        </span>
        <span className="mt-2 text-sm font-semibold text-foreground">
          Curtailed in 2023
        </span>
        <span className="mt-1 text-xs text-muted-foreground">
          Enough to power 1.3 million homes
        </span>
      </div>
    );
  }

  return (
    <div className="relative flex flex-col bg-card px-6 py-8">
      {/* Live indicator */}
      <div className="absolute top-3 right-3">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-primary" />
        </span>
      </div>
      <span className="font-serif text-3xl font-bold text-primary">
        {data.month.energy_gwh} GWh
      </span>
      <span className="mt-2 text-sm font-semibold text-foreground">
        Curtailed this month
      </span>
      <a
        href="https://curtailcoin.com"
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-primary"
      >
        Live data from CurtailCoin
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

export function NumbersSection() {
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
    <section id="numbers" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          By The Numbers
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          The scale of the opportunity
        </h2>

        <div className="mt-16 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {/* Live card from CurtailCoin */}
          <LiveCard data={data} loading={loading} />

          {/* Static cards */}
          {staticCards.map((card) => (
            <div key={card.label} className="flex flex-col bg-card px-6 py-8">
              <span className="font-serif text-3xl font-bold text-primary">
                {card.value}
              </span>
              <span className="mt-2 text-sm font-semibold text-foreground">
                {card.label}
              </span>
              <span className="mt-1 text-xs text-muted-foreground">
                {card.context}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
