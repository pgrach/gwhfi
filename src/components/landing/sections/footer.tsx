const sectionLinks = [
  { label: "Problem", href: "#problem" },
  { label: "Solution", href: "#solution" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "Live Dashboard", href: "https://www.gwhfi.com/dashboard", external: true },
  { label: "Numbers", href: "#numbers" },
  { label: "Partners", href: "#partners" },
  { label: "Roadmap", href: "#roadmap" },
];

export function Footer() {
  return (
    <footer className="border-t border-border px-6 py-16">
      <div className="mx-auto max-w-6xl">
        <div className="grid grid-cols-1 gap-12 md:grid-cols-4">
          {/* Brand */}
          <div className="md:col-span-2">
            <span className="font-serif text-xl font-bold text-foreground">
              GWhFi
            </span>
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
              Programmable ASIC heaters turning surplus renewable energy
              into hot water, Bitcoin revenue, and grid flexibility
              payments.
            </p>
            <a
              href="mailto:pavel@aidala.uk"
              className="mt-4 inline-block text-sm font-medium text-primary transition-colors hover:text-primary/80"
            >
              pavel@aidala.uk
            </a>
          </div>

          {/* Links */}
          <div>
            <h4 className="mb-4 text-xs font-medium tracking-widest text-muted-foreground uppercase">
              Sections
            </h4>
            <ul className="flex flex-col gap-2.5">
              {sectionLinks.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-primary"
                    {...(link.external
                      ? {
                        target: "_blank",
                        rel: "noopener noreferrer",
                      }
                      : {})}
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="mb-4 text-xs font-medium tracking-widest text-muted-foreground uppercase">
              Legal
            </h4>
            <ul className="flex flex-col gap-2.5">
              <li>
                <span className="text-sm text-muted-foreground">
                  Privacy Policy
                </span>
              </li>
              <li>
                <span className="text-sm text-muted-foreground">
                  Terms of Service
                </span>
              </li>
              <li>
                <a
                  href="https://gwhfi.com"
                  className="text-sm text-muted-foreground transition-colors hover:text-primary"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  gwhfi.com
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-border pt-8 md:flex-row">
          <span className="text-xs text-muted-foreground">
            {"\u00A9"} {new Date().getFullYear()} GWhFi Ltd. All rights
            reserved. Registered in England and Wales.
          </span>
          <span className="text-xs text-muted-foreground">
            Turning wasted energy into heat and revenue.
          </span>
        </div>
      </div>
    </footer>
  );
}
