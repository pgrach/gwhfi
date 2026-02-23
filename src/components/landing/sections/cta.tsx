"use client";

import { FormEvent, useState } from "react";
import { Handshake } from "lucide-react";

interface FormState {
  name: string;
  email: string;
  organization: string;
  siteType: string;
  message: string;
  website: string;
}

const initialState: FormState = {
  name: "",
  email: "",
  organization: "",
  siteType: "",
  message: "",
  website: "",
};

export function CTASection() {
  const [form, setForm] = useState<FormState>(initialState);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("loading");
    setErrorMessage("");

    try {
      const response = await fetch("/api/pilot-lead", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(form),
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(data?.error ?? "Could not submit your request");
      }

      setStatus("success");
      setForm(initialState);
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Could not submit your request");
    }
  }

  return (
    <section id="contact" className="border-t border-border px-6 py-24 md:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 text-xs font-medium tracking-widest text-primary uppercase">
          Get Involved
        </div>
        <h2 className="max-w-3xl font-serif text-3xl font-bold leading-tight text-foreground md:text-5xl text-balance">
          Running renewable assets or hot-water infrastructure?
        </h2>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground text-pretty">
          Book a 20-minute pilot call. We will assess site fit, expected energy
          absorption, and commercial structure for a first deployment.
        </p>

        <div className="mt-12 rounded-lg border border-primary/30 bg-primary/5 p-8 md:p-10">
          <div className="mb-6 max-w-2xl">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-md bg-primary/10">
              <Handshake className="h-6 w-6 text-primary" />
            </div>
            <h3 className="font-serif text-2xl font-semibold text-foreground">
              Start with a commercial pilot
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Best fit today: sites with high hot-water demand and access to
              flexible power.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <input
              type="text"
              value={form.website}
              onChange={(event) =>
                setForm((current) => ({ ...current, website: event.target.value }))
              }
              className="hidden"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
            />

            <div className="flex flex-col gap-1.5">
              <label htmlFor="pilot-name" className="text-xs font-medium text-muted-foreground">
                Name
              </label>
              <input
                id="pilot-name"
                required
                value={form.name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, name: event.target.value }))
                }
                className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-primary focus:outline-none"
                placeholder="Your name"
                suppressHydrationWarning
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="pilot-email" className="text-xs font-medium text-muted-foreground">
                Work email
              </label>
              <input
                id="pilot-email"
                type="email"
                required
                value={form.email}
                onChange={(event) =>
                  setForm((current) => ({ ...current, email: event.target.value }))
                }
                className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-primary focus:outline-none"
                placeholder="name@company.com"
                suppressHydrationWarning
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="pilot-org" className="text-xs font-medium text-muted-foreground">
                Organisation
              </label>
              <input
                id="pilot-org"
                required
                value={form.organization}
                onChange={(event) =>
                  setForm((current) => ({ ...current, organization: event.target.value }))
                }
                className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-primary focus:outline-none"
                placeholder="Company or site name"
                suppressHydrationWarning
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="pilot-site" className="text-xs font-medium text-muted-foreground">
                Site type
              </label>
              <select
                id="pilot-site"
                required
                value={form.siteType}
                onChange={(event) =>
                  setForm((current) => ({ ...current, siteType: event.target.value }))
                }
                className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                suppressHydrationWarning
              >
                <option value="">Select site type</option>
                <option value="generator">Renewable generator</option>
                <option value="commercial">Commercial hot-water site</option>
                <option value="aggregator">Aggregator / energy services</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5 md:col-span-2">
              <label htmlFor="pilot-message" className="text-xs font-medium text-muted-foreground">
                Pilot context (optional)
              </label>
              <textarea
                id="pilot-message"
                rows={4}
                value={form.message}
                onChange={(event) =>
                  setForm((current) => ({ ...current, message: event.target.value }))
                }
                className="rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-primary focus:outline-none"
                placeholder="Site location, current hot-water setup, or pilot timeline"
              />
            </div>

            <div className="md:col-span-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="submit"
                disabled={status === "loading"}
                className="inline-flex items-center justify-center rounded-md bg-primary px-7 py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70"
                suppressHydrationWarning
              >
                {status === "loading" ? "Submitting..." : "Book Pilot Call"}
              </button>

              <p className="text-xs text-muted-foreground">
                Prefer email? <a href="mailto:pavel@aidala.uk" className="text-primary hover:text-primary/80">pavel@aidala.uk</a>
              </p>
            </div>

            {status === "success" && (
              <p className="md:col-span-2 text-sm text-primary">
                Thanks. Your request is in. We will reply within 1 business day.
              </p>
            )}

            {status === "error" && (
              <p className="md:col-span-2 text-sm text-destructive">
                {errorMessage}
              </p>
            )}
          </form>

          <div className="mt-6 border-t border-border/60 pt-4 text-xs text-muted-foreground">
            <span className="font-medium text-muted-foreground/90">Other enquiries:</span>
            <span className="ml-2">
              <a
                href="mailto:pavel@aidala.uk?subject=Investor%20Briefing%20Request"
                className="transition-colors hover:text-primary"
              >
                Investor briefing
              </a>
              <span className="mx-2 text-muted-foreground/60">•</span>
              <a
                href="mailto:pavel@aidala.uk?subject=Domestic%20Waitlist"
                className="transition-colors hover:text-primary"
              >
                Domestic waitlist
              </a>
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
