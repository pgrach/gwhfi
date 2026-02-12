import { Zap, TrendingDown, Leaf } from "lucide-react";

const stats = [
  {
    icon: Zap,
    value: "4.6 TWh",
    label: "Clean energy curtailed annually in the UK",
  },
  {
    icon: TrendingDown,
    value: "\u00A31.46B",
    label: "Annual cost of constraint payments",
  },
  {
    icon: Leaf,
    value: "0 CO\u2082",
    label: "Additional emissions from our solution",
  },
];

export function HeroSection() {
  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center px-6 pt-20">
      {/* Subtle grid pattern */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(hsl(172, 100%, 35%) 1px, transparent 1px), linear-gradient(90deg, hsl(172, 100%, 35%) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
        aria-hidden="true"
      />

      <div className="relative z-10 mx-auto max-w-4xl text-center">
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-1.5">
          <span className="h-2 w-2 rounded-full bg-primary" />
          <span className="text-xs font-medium tracking-wide text-primary uppercase">
            Coming out of stealth
          </span>
        </div>

        <h1 className="font-serif text-4xl font-bold leading-tight tracking-tight text-foreground md:text-6xl lg:text-7xl text-balance">
          Turn Curtailed Energy Into Hot Water and Cashflow
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground md:text-xl text-pretty">
          We replace immersion heaters with programmable ASIC units that absorb
          surplus renewable power and create three outputs: hot water, Bitcoin
          revenue, and demand flexibility income.
        </p>

        <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
          <a
            href="#contact"
            className="rounded-md bg-primary px-8 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Book Pilot Call
          </a>
          <a
            href="#solution"
            className="rounded-md border border-border px-8 py-3 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
          >
            See How It Works
          </a>
        </div>
      </div>

      {/* Stats bar */}
      <div className="relative z-10 mx-auto mt-20 w-full max-w-4xl">
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-3">
          {stats.map((stat) => (
            <div
              key={stat.value}
              className="flex flex-col items-center gap-3 bg-card px-6 py-8"
            >
              <stat.icon className="h-5 w-5 text-primary" />
              <span className="font-serif text-3xl font-bold text-foreground">
                {stat.value}
              </span>
              <span className="text-center text-sm text-muted-foreground">
                {stat.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
