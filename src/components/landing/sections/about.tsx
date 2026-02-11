export function AboutSection() {
  return (
    <section id="about" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          About
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          The team behind GWhFi
        </h2>

        <div className="mt-12 max-w-3xl rounded-lg border border-border bg-card p-8">
          <div className="flex flex-col gap-6 sm:flex-row">
            {/* Founder photo */}
            <img
              src="/founder.jpg"
              alt="Pavel Grachev"
              className="h-20 w-20 shrink-0 rounded-full object-cover"
            />
            <div>
              <h3 className="font-serif text-xl font-semibold text-foreground">
                Pavel Grachev
              </h3>
              <p className="text-sm font-medium text-primary">
                Founder
              </p>
              <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                Pavel is a technologist with
                deep experience across grid infrastructure, distributed
                energy resources, and programmable hardware. He founded
                GWhFi to solve a simple but costly problem: the UK
                generates more clean energy than it can use, while
                millions of hot water cylinders sit idle as untapped
                thermal stores. GWhFi bridges that gap with
                purpose-built hardware that turns waste into value.
              </p>
              <a
                href="mailto:pavel@aidala.uk"
                className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary transition-colors hover:text-primary/80"
              >
                pavel@aidala.uk
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
