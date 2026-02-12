import { Flame, Bitcoin, Cable } from "lucide-react";

const streams = [
  {
    icon: Flame,
    title: "Hot Water",
    description:
      "Our ASIC heater replaces a standard immersion element. Compute power is captured as heat and stored in the cylinder for domestic hot water.",
    detail: "100% thermal capture",
  },
  {
    icon: Bitcoin,
    title: "Bitcoin Revenue",
    description:
      "While heating water, the device mines Bitcoin. That revenue helps offset operating costs and can improve pilot economics.",
    detail: "Passive income stream",
  },
  {
    icon: Cable,
    title: "Grid Flexibility Payments",
    description:
      "Aggregated units can act as controllable demand, absorbing surplus generation and participating in flexibility programs where eligible.",
    detail: "Demand-side response",
  },
];

export function SolutionSection() {
  return (
    <section id="solution" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          The Solution
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          One device. Three value streams.
        </h2>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground text-pretty">
          GWhFi is a programmable ASIC heater for standard hot-water cylinders.
          It turns surplus electricity into heat and monetisable compute, with
          flexibility participation layered in as deployments scale.
        </p>

        <div className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-3">
          {streams.map((stream, i) => (
            <div
              key={stream.title}
              className="group relative flex flex-col rounded-lg border border-border bg-card p-8 transition-colors hover:border-primary/40"
            >
              <div className="mb-1 text-xs font-medium text-primary/60">
                {"0"}
                {i + 1}
              </div>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-md bg-primary/10">
                <stream.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-2 font-serif text-xl font-semibold text-foreground">
                {stream.title}
              </h3>
              <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
                {stream.description}
              </p>
              <div className="mt-6 inline-flex items-center gap-2 border-t border-border pt-4">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                <span className="text-xs font-medium text-primary">
                  {stream.detail}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
