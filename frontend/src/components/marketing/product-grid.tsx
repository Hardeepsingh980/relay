"use client";

import { Headphones, Radar, Repeat2, Search } from "lucide-react";

import { AGENT_COLOR, useLanding } from "@/components/marketing/landing-hero";
import { Reveal, Spotlight } from "@/components/marketing/motion";

const PRODUCT = [
  {
    icon: Radar,
    name: "Account Health",
    body: "Finds customers who look fine in HubSpot but are about to leave. It shows the chain: who left, which tickets share one bug, which feature they stopped using. Then it drafts a save plan for you to approve.",
    under: "Multi-hop Cypher across contacts, tickets, bugs, features and weekly usage.",
    rgb: "229, 72, 77",
  },
  {
    icon: Repeat2,
    name: "Handovers",
    body: "When someone resigns, Relay finds what only they know. They answer short questions about their own work, and the person who takes over starts with every answer.",
    under: "A remove-person query over expertise scores built from commits, threads and tickets.",
    rgb: "10, 143, 230",
  },
  {
    icon: Headphones,
    name: "Sales Assist",
    body: "A brief before the call. Cards during the call with roadmap dates, known bugs and past promises. A summary and a follow-up draft after it.",
    under: "Each line of the call triggers graph lookups in milliseconds. Type or speak your own lines to test it.",
    rgb: "239, 138, 0",
  },
  {
    icon: Search,
    name: "Ask",
    body: "Ask why something works the way it does. Every claim links to its source, and you see the path Relay took through the graph.",
    under: "Full-text search and graph walks find the facts. Gemini writes the answer from them.",
    rgb: "18, 165, 148",
  },
];

export function ProductGrid() {
  const { data } = useLanding();
  const chip = (agent: string) => data?.stories.find((s) => s.agent === agent)?.chip;
  return (
    <div className="mt-10 grid gap-4 md:grid-cols-2">
      {PRODUCT.map((p, i) => {
        const live = chip(p.name);
        return (
          <Reveal key={p.name} delay={i * 90}>
            <Spotlight color={p.rgb} className="h-full rounded-2xl border bg-card p-7 transition-shadow duration-500 hover:shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
              <span
                className="flex size-10 items-center justify-center rounded-xl transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110"
                style={{ background: `rgba(${p.rgb}, 0.1)`, color: `rgb(${p.rgb})` }}
              >
                <p.icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-5 text-[20px] font-semibold tracking-[-0.2px]">{p.name}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-foreground/75">{p.body}</p>
              {live ? (
                <p className="mt-4 inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-[12.5px] font-medium">
                  <span className="relative flex size-1.5">
                    <span className="absolute inline-flex size-full animate-ping rounded-full opacity-75" style={{ background: AGENT_COLOR[p.name] }} />
                    <span className="relative inline-flex size-1.5 rounded-full" style={{ background: AGENT_COLOR[p.name] }} />
                  </span>
                  {live}
                </p>
              ) : null}
              <p className="mt-5 border-t pt-3 text-[13px] text-muted-foreground">{p.under}</p>
            </Spotlight>
          </Reveal>
        );
      })}
    </div>
  );
}
