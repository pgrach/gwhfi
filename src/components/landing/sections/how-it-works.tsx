"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Home, Building2, Network, ArrowRight } from "lucide-react";

const flowSteps = [
  { label: "Surplus Renewable Energy", sub: "Wind / Solar" },
  { label: "GWhFi ASIC Heater", sub: "Compute + Heat" },
  { label: "Hot Water Cylinder", sub: "Thermal Store" },
  { label: "Grid / Bitcoin / Heat", sub: "Three Outputs" },
];

const deployments = [
  {
    value: "domestic",
    icon: Home,
    title: "Domestic",
    description:
      "A single GWhFi unit replaces the immersion element in a household hot water cylinder. It connects to the home Wi-Fi and is remotely managed by our aggregation platform. Homeowners receive hot water and a share of Bitcoin and flexibility revenue. No lifestyle changes required.",
    specs: [
      { label: "Power", value: "2 kW" },
      { label: "Fits", value: "Standard UK cylinder" },
      { label: "Control", value: "Cloud-managed" },
    ],
  },
  {
    value: "commercial",
    icon: Building2,
    title: "Commercial",
    description:
      "Multi-unit deployments in hotels, care homes, leisure centres, and student accommodation. Larger hot water demand means higher utilisation and revenue. GWhFi provides full system design, installation, and operational management under a service-level agreement.",
    specs: [
      { label: "Power", value: "10-100 kW" },
      { label: "Sites", value: "High hot-water demand" },
      { label: "Model", value: "Managed service" },
    ],
  },
  {
    value: "aggregation",
    icon: Network,
    title: "Aggregation Platform",
    description:
      "Thousands of GWhFi units, both domestic and commercial, aggregate into a single virtual power plant. The platform receives dispatch signals from NESO and activates or deactivates heaters in real time to absorb excess generation and provide frequency response.",
    specs: [
      { label: "Scale", value: "GW-class fleet" },
      { label: "Response", value: "Sub-second dispatch" },
      { label: "Revenue", value: "FFR / DC / BM" },
    ],
  },
];

export function HowItWorksSection() {
  return (
    <section
      id="how-it-works"
      className="border-t border-border px-6 py-24 md:py-32"
    >
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          How It Works
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          From surplus electrons to hot water and revenue
        </h2>

        {/* Flow diagram */}
        <div className="mt-16 flex flex-col items-center gap-2 md:flex-row md:gap-0">
          {flowSteps.map((step, i) => (
            <div key={step.label} className="flex items-center gap-2 md:flex-1">
              <div className="flex flex-1 flex-col items-center rounded-lg border border-border bg-card px-4 py-6 text-center">
                <span className="mb-1 text-xs font-medium text-primary">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-sm font-semibold text-foreground">
                  {step.label}
                </span>
                <span className="mt-1 text-xs text-muted-foreground">
                  {step.sub}
                </span>
              </div>
              {i < flowSteps.length - 1 && (
                <ArrowRight className="hidden h-4 w-4 shrink-0 text-primary md:block" />
              )}
            </div>
          ))}
        </div>

        {/* Accordion deployments */}
        <div className="mt-16">
          <Accordion type="single" collapsible defaultValue="domestic">
            {deployments.map((dep) => (
              <AccordionItem
                key={dep.value}
                value={dep.value}
                className="border-border"
              >
                <AccordionTrigger className="py-6 text-base font-semibold text-foreground hover:no-underline hover:text-primary">
                  <div className="flex items-center gap-3">
                    <dep.icon className="h-5 w-5 text-primary" />
                    {dep.title}
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="pb-4">
                    <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      {dep.description}
                    </p>
                    <div className="mt-6 flex flex-wrap gap-4">
                      {dep.specs.map((spec) => (
                        <div
                          key={spec.label}
                          className="flex flex-col rounded-md border border-border bg-secondary px-4 py-3"
                        >
                          <span className="text-xs text-muted-foreground">
                            {spec.label}
                          </span>
                          <span className="text-sm font-semibold text-foreground">
                            {spec.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  );
}
