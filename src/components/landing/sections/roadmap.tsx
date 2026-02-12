import { Check } from "lucide-react";

const phases = [
  {
    phase: "01",
    title: "Market Analysis",
    period: "Completed",
    status: "done" as const,
    description:
      "Curtailment data analysis, economic modelling, and identification of the UK hot water cylinder opportunity.",
  },
  {
    phase: "02",
    title: "Research Partnerships",
    period: "Completed",
    status: "done" as const,
    description:
      "Collaboration with Universities on thermodynamic and grid integration feasibility.",
  },
  {
    phase: "03",
    title: "Hardware Prototype",
    period: "Completed",
    status: "done" as const,
    description:
      "First ASIC heater prototype built with Winchain, validated in lab conditions for heat output and hash rate.",
  },
  {
    phase: "04",
    title: "Commercial Pilot",
    period: "In progress",
    status: "active" as const,
    description:
      "Initial deployment in commercial hot water systems. Real-world data on energy absorption, revenue, and grid interaction.",
  },
  {
    phase: "05",
    title: "Aggregation Platform",
    period: "Planned",
    status: "upcoming" as const,
    description:
      "Cloud-based fleet management, NESO integration, and demand-side response qualification.",
  },
  {
    phase: "06",
    title: "Domestic Pilot",
    period: "Planned",
    status: "upcoming" as const,
    description:
      "Scaled deployment into UK households. Consumer-ready product, installer partnerships, and national rollout preparation.",
  },
];

export function RoadmapSection() {
  return (
    <section id="roadmap" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          Roadmap
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          From analysis to national deployment
        </h2>

        <div className="relative mt-16">
          {/* Timeline line */}
          <div className="absolute top-0 bottom-0 left-[19px] hidden w-px bg-border md:block" />

          <div className="flex flex-col gap-8">
            {phases.map((phase) => (
              <div key={phase.phase} className="flex gap-6">
                {/* Timeline dot */}
                <div className="relative hidden shrink-0 md:flex">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-full border-2 ${phase.status === "done"
                        ? "border-primary bg-primary"
                        : phase.status === "active"
                          ? "border-primary bg-primary/20"
                          : "border-border bg-card"
                      }`}
                  >
                    {phase.status === "done" ? (
                      <Check className="h-4 w-4 text-primary-foreground" />
                    ) : (
                      <span
                        className={`text-xs font-bold ${phase.status === "active"
                            ? "text-primary"
                            : "text-muted-foreground"
                          }`}
                      >
                        {phase.phase}
                      </span>
                    )}
                  </div>
                </div>

                {/* Content */}
                <div
                  className={`flex-1 rounded-lg border p-6 ${phase.status === "active"
                      ? "border-primary/40 bg-primary/5"
                      : "border-border bg-card"
                    }`}
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-serif text-lg font-semibold text-foreground">
                      {phase.title}
                    </span>
                    <span className="rounded-full border border-border bg-secondary px-2.5 py-0.5 text-xs text-muted-foreground">
                      {phase.period}
                    </span>
                    {phase.status === "done" && (
                      <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                        Complete
                      </span>
                    )}
                    {phase.status === "active" && (
                      <span className="rounded-full bg-primary/20 px-2.5 py-0.5 text-xs font-medium text-primary">
                        In Progress
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {phase.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
