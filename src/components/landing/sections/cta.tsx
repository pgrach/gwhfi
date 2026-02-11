import { Handshake, LineChart, Home } from "lucide-react";

const paths = [
  {
    icon: Handshake,
    title: "Generators & Partners",
    description:
      "You operate renewable assets or manage hot water infrastructure. Let's explore a pilot deployment together.",
    action: "Discuss Partnership",
    href: "mailto:pavel@aidala.uk?subject=Partnership%20Enquiry",
  },
  {
    icon: LineChart,
    title: "Investors",
    description:
      "Interested in the energy flexibility market? Request a briefing on our technology, traction, and roadmap.",
    action: "Request Briefing",
    href: "mailto:pavel@aidala.uk?subject=Investor%20Briefing%20Request",
  },
  {
    icon: Home,
    title: "Homeowners",
    description:
      "Want a GWhFi heater in your hot water cylinder? Join the waitlist for our domestic pilot launching 2026-27.",
    action: "Join Waitlist",
    href: "mailto:pavel@aidala.uk?subject=Domestic%20Waitlist",
  },
];

export function CTASection() {
  return (
    <section id="contact" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          Get Involved
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          Ready to turn wasted energy into value?
        </h2>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground text-pretty">
          Whether you are a generator, investor, or homeowner, there is a path to
          work with GWhFi.
        </p>

        <div className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-3">
          {paths.map((path) => (
            <div
              key={path.title}
              className="flex flex-col rounded-lg border border-border bg-card p-8 transition-colors hover:border-primary/40"
            >
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-md bg-primary/10">
                <path.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-2 font-serif text-xl font-semibold text-foreground">
                {path.title}
              </h3>
              <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
                {path.description}
              </p>
              <a
                href={path.href}
                className="mt-6 inline-flex items-center justify-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                {path.action}
              </a>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
