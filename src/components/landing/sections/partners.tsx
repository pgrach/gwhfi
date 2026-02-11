import { GraduationCap, Radio, Cpu, Factory } from "lucide-react";

const partnerGroups = [
  {
    icon: GraduationCap,
    category: "Research",
    partners: ["Cardiff University", "TU Shannon"],
    description:
      "Academic partners validating thermodynamic models and grid integration strategies.",
  },
  {
    icon: Radio,
    category: "Grid",
    partners: ["NESO", "Ofgem"],
    description:
      "Regulatory and system operator engagement for flexibility market access.",
  },
  {
    icon: Cpu,
    category: "Hardware",
    partners: ["Winchain", "HeatCore", "Superheat", "Canaan", "MicroBT", "Bitmain"],
    description:
      "ASIC hardware partners providing mining-grade silicon optimised for thermal deployment.",
  },
  {
    icon: Factory,
    category: "Industry",
    partners: ["Energy sector partners"],
    description:
      "Working with generators, DNOs, and hot water cylinder manufacturers to integrate across the value chain.",
  },
];

export function PartnersSection() {
  return (
    <section id="partners" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          Partners
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          Built with the ecosystem
        </h2>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground text-pretty">
          GWhFi collaborates across research, regulation, hardware, and
          industry to deliver a fully integrated energy flexibility platform.
        </p>

        <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2">
          {partnerGroups.map((group) => (
            <div
              key={group.category}
              className="flex gap-4 rounded-lg border border-border bg-card p-6"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
                <group.icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3 className="font-serif text-lg font-semibold text-foreground">
                  {group.category}
                </h3>
                <div className="mt-1 flex flex-wrap gap-2">
                  {group.partners.map((p) => (
                    <span
                      key={p}
                      className="rounded-full border border-border bg-secondary px-3 py-0.5 text-xs font-medium text-foreground"
                    >
                      {p}
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {group.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
