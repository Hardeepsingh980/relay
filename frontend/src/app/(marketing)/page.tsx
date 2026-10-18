import Link from "next/link";
import { ArrowRight, Bot, GitBranch, Network, ShieldCheck, Workflow } from "lucide-react";

import { AgentTrace } from "@/components/marketing/agent-trace";
import { LandingHero } from "@/components/marketing/landing-hero";
import { LogoMarquee } from "@/components/marketing/logo-marquee";
import { MarketingNav } from "@/components/marketing/marketing-nav";
import { Reveal } from "@/components/marketing/motion";
import { ProductGrid } from "@/components/marketing/product-grid";

const HOW = [
  {
    icon: Network,
    title: "One graph per company",
    body: "FalkorDB holds customers, people, tickets, messages, meetings and decisions. Each workspace works on its own copy.",
  },
  {
    icon: Workflow,
    title: "Five agents, one memory",
    body: "Ingest, Account Health, Handover, Onboarding and Sales Assist read and write the same graph. That is how work passes between them.",
  },
  {
    icon: Bot,
    title: "Tools any AI can use",
    body: "The agents use 23 graph tools. The same tools are open to other AI apps through MCP.",
  },
  {
    icon: ShieldCheck,
    title: "People stay in charge",
    body: "Gemini plans investigations and writes answers. Every action waits for a person to approve it.",
  },
];

export default function Landing() {
  return (
    <div className="min-h-dvh bg-background">
      <MarketingNav />
      <LandingHero />

      <section className="mx-auto max-w-[1240px] px-5 pb-6 pt-16 md:px-8">
        <Reveal>
          <p className="text-center text-[14px] text-muted-foreground">Relay reads from the tools your team already uses</p>
        </Reveal>
        <LogoMarquee />
      </section>

      <section id="product" className="mx-auto max-w-[1240px] scroll-mt-20 px-5 py-20 md:px-8">
        <Reveal>
          <p className="text-[13px] font-medium text-primary">Four agents</p>
          <h2 className="mt-2 max-w-[640px] text-[34px] font-semibold leading-[1.1] tracking-[-0.8px] sm:text-[40px]">
            They watch your customers and your team, so nothing slips.
          </h2>
        </Reveal>
        <ProductGrid />
      </section>

      <AgentTrace />

      <section id="repos" className="mx-auto max-w-[1240px] scroll-mt-20 px-5 py-20 md:px-8">
        <Reveal>
          <div className="relative overflow-hidden rounded-[28px] border bg-card p-8 shadow-panel md:p-12">
            <div aria-hidden className="paper-dots absolute inset-y-0 right-0 w-1/2 [mask-image:linear-gradient(to_left,black,transparent)]" />
            <div className="relative flex flex-col gap-8 md:flex-row md:items-center">
              <div className="flex-1">
                <span className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-primary">
                  <GitBranch className="size-5" aria-hidden />
                </span>
                <h2 className="mt-5 text-[30px] font-semibold tracking-[-0.6px]">Try it on your own code</h2>
                <p className="mt-3 max-w-[620px] text-[16px] leading-relaxed text-muted-foreground">
                  Paste any public GitHub repo. Relay reads its history into a graph of who changed what. It shows what only
                  one person knows, what leaves with each person, and who is central. Then you can ask questions about it.
                </p>
              </div>
              <Link
                href="/sign-in?next=/repos"
                className="group inline-flex h-11 shrink-0 items-center gap-2 self-start rounded-full bg-foreground px-5 text-[15px] font-medium text-background transition hover:opacity-90 md:self-center"
              >
                Analyze a repo <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </div>
          </div>
        </Reveal>
      </section>

      <section id="how" className="mx-auto max-w-[1240px] scroll-mt-20 px-5 pb-24 md:px-8">
        <Reveal>
          <h2 className="text-[34px] font-semibold tracking-[-0.8px]">How it works</h2>
        </Reveal>
        <div className="relative mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div aria-hidden className="absolute left-5 right-5 top-5 hidden h-px bg-[linear-gradient(90deg,transparent,var(--border)_10%,var(--border)_90%,transparent)] lg:block" />
          {HOW.map((h, i) => (
            <Reveal key={h.title} delay={i * 110}>
              <span className="relative flex size-10 items-center justify-center rounded-xl border bg-card text-primary shadow-panel">
                <h.icon className="size-[18px]" aria-hidden />
              </span>
              <h3 className="mt-5 text-[16.5px] font-semibold">{h.title}</h3>
              <p className="mt-1.5 text-[14.5px] leading-relaxed text-muted-foreground">{h.body}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="px-3 pb-6 md:px-6">
        <div className="relative isolate mx-auto max-w-[1240px] overflow-hidden rounded-[28px] border bg-card px-6 py-16 text-center shadow-[0_1px_2px_rgba(15,23,42,0.04),0_16px_48px_rgba(15,23,42,0.06)] md:py-20">
          <div aria-hidden className="paper-dots absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_50%_0%,black,transparent_70%)]" />
          <Reveal>
            <h2 className="mx-auto max-w-[720px] text-[34px] font-semibold leading-[1.1] tracking-[-0.8px] sm:text-[44px]">
              See it work on a real company graph.
            </h2>
            <p className="mx-auto mt-4 max-w-[520px] text-[16.5px] leading-relaxed text-muted-foreground">
              Cheerio is a sample company with synthetic data. Each visitor gets a private copy of its workspace, with every agent working.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link
                href="/sign-in"
                className="group inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-[15px] font-medium text-primary-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08),0_6px_18px_rgba(0,138,232,0.28)] transition hover:-translate-y-px"
              >
                Try it now <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <Link
                href="/sign-in?next=/graph"
                className="inline-flex h-11 items-center gap-2 rounded-full border bg-card px-5 text-[15px] font-medium shadow-panel transition hover:-translate-y-px hover:bg-accent"
              >
                <Network className="size-4" /> Open the knowledge graph
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <footer>
        <div className="mx-auto flex max-w-[1240px] flex-col gap-2 px-5 py-8 text-[13px] text-muted-foreground md:flex-row md:items-center md:justify-between md:px-8">
          <p>Relay · built for FalkorDB Graph Hacks</p>
          <p>Cheerio is a sample company with synthetic data. Repo knowledge uses public GitHub data.</p>
        </div>
      </footer>
    </div>
  );
}
