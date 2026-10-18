"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { ArrowRight, GitBranch } from "lucide-react";

import { HeroGraph, STEP_MS, TYPE_COLOR } from "@/components/marketing/hero-graph";
import { CountUp, Typewriter, useReducedMotion } from "@/components/marketing/motion";
import { publicApi } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The landing page's one request: a real slice of Cheerio's graph and what three agents found in it. */
export function useLanding() {
  return useSWR("/api/public/graph", publicApi.graph, { revalidateOnFocus: false });
}

export const AGENT_COLOR: Record<string, string> = {
  "Account Health": "#e5484d",
  Handovers: "#0a8fe6",
  "Sales Assist": "#ef8a00",
};

const LEGEND = [
  ["People", TYPE_COLOR.Person],
  ["Customers", TYPE_COLOR.Account],
  ["Product", TYPE_COLOR.Feature],
  ["Bugs", TYPE_COLOR.Bug],
  ["Decisions", TYPE_COLOR.Decision],
];

const RISE = "animate-[relay-rise_0.9s_var(--ease-out-soft)_both]";
const rise = (delay: number) => ({ animationDelay: `${delay}ms` });

export function LandingHero() {
  const { data, error } = useLanding();
  const reduced = useReducedMotion();
  const [story, setStory] = useState(0);
  const [paused, setPaused] = useState(false);
  // Bumped on every tab click, so clicking the current story plays it again from the start.
  const [run, setRun] = useState(0);
  const stories = data?.stories ?? [];
  const current = stories[story];
  const dwell = current ? current.path.length * STEP_MS + 4800 : 6000;
  const next = () => setStory((s) => (stories.length ? (s + 1) % stories.length : 0));
  const p = data?.preview;

  return (
    <section id="hero" className="relative isolate overflow-hidden bg-background">
      <div aria-hidden className="paper-dots absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_72%_45%,black,transparent_68%)]" />

      <div className="mx-auto flex min-h-[max(100dvh,760px)] max-w-[1240px] flex-col px-5 pb-7 pt-28 md:px-8 lg:pointer-events-none lg:pt-32">
        <div className="relative z-10 max-w-[590px] lg:pointer-events-auto">
          <p className={cn("inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-[12.5px] text-muted-foreground shadow-panel", RISE)}>
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-covered opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-covered" />
            </span>
            Live: Cheerio&apos;s company graph on FalkorDB
          </p>
          <h1 className={cn("mt-5 text-[44px] font-semibold leading-[1.03] tracking-[-1.6px] sm:text-[60px]", RISE)} style={rise(80)}>
            Keep your customers, and <span className="text-primary">keep what your people know.</span>
          </h1>
          <p className={cn("mt-5 max-w-[520px] text-[17.5px] leading-relaxed text-muted-foreground", RISE)} style={rise(170)}>
            Relay puts HubSpot, support, product usage, Slack, Jira, docs and calls into one graph. Agents read it, find the
            cause, show the proof, and act when you approve.
          </p>
          <div className={cn("mt-8 flex flex-wrap gap-3", RISE)} style={rise(260)}>
            <Link
              href="/sign-in"
              className="group inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-[15px] font-medium text-primary-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08),0_6px_18px_rgba(0,138,232,0.28)] transition hover:-translate-y-px hover:shadow-[0_1px_2px_rgba(0,0,0,0.08),0_10px_24px_rgba(0,138,232,0.34)]"
            >
              Try it now <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/sign-in?next=/repos"
              className="inline-flex h-11 items-center gap-2 rounded-full border bg-card px-5 text-[15px] font-medium shadow-panel transition hover:-translate-y-px hover:bg-accent"
            >
              <GitBranch className="size-4" /> Analyze a GitHub repo
            </Link>
          </div>

          {/* What the agents found, in step with the graph. */}
          <div
            className={cn(
              "mt-9 rounded-2xl border bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_32px_rgba(15,23,42,0.07)]",
              RISE,
            )}
            style={rise(350)}
            onPointerEnter={() => setPaused(true)}
            onPointerLeave={() => setPaused(false)}
          >
            <div className="flex gap-2.5" role="tablist" aria-label="What the agents found">
              {(stories.length ? stories : [{ agent: "Account Health" }, { agent: "Handovers" }, { agent: "Sales Assist" }]).map((s, i) => {
                const color = AGENT_COLOR[s.agent] ?? "#262626";
                const active = i === story && !!current;
                return (
                  <button key={s.agent} role="tab" aria-selected={active} onClick={() => {
                      setStory(i);
                      setRun((r) => r + 1);
                    }}
                    disabled={!stories.length} className="group flex-1 text-left">
                    <span className="block h-[3px] overflow-hidden rounded-full bg-muted">
                      <span
                        key={`${story}-${i}-${run}`}
                        className="block h-full origin-left rounded-full"
                        style={{
                          background: color,
                          transform: i < story || (active && reduced) ? "scaleX(1)" : active ? undefined : "scaleX(0)",
                          animationName: active && !reduced ? "relay-fill" : "none",
                          animationDuration: `${dwell}ms`,
                          animationTimingFunction: "linear",
                          animationFillMode: "forwards",
                          animationPlayState: paused ? "paused" : "running",
                        }}
                        onAnimationEnd={active ? next : undefined}
                      />
                    </span>
                    <span
                      className={cn(
                        "mt-2 block text-[12.5px] font-medium transition-colors",
                        active ? "text-foreground" : "text-muted-foreground group-hover:text-foreground",
                      )}
                    >
                      {s.agent}
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="mt-3 min-h-[76px] text-[15px] leading-relaxed text-foreground/85">
              {current ? (
                <Typewriter key={`${story}-${run}`} text={current.text} />
              ) : error ? (
                "Could not reach the graph. Refresh to try again."
              ) : (
                <span className="text-muted-foreground">Reading the graph…</span>
              )}
            </p>
            {current ? (
              <p className="mt-1 flex items-center gap-2 text-[12px] text-muted-foreground">
                <span className="size-1.5 rounded-full" style={{ background: AGENT_COLOR[current.agent] }} />
                {current.agent} walked {current.path.length} nodes in the graph. Hover the graph to explore.
              </p>
            ) : null}
          </div>
        </div>

        {/* The graph: its own block on phones, the whole hero behind the text on wide screens. */}
        <div className="relative -mx-5 mt-6 h-[380px] lg:pointer-events-auto lg:absolute lg:inset-0 lg:mx-0 lg:mt-0 lg:h-auto">
          <HeroGraph data={data} story={story} run={run} className="absolute inset-0" />
          <div aria-hidden className="pointer-events-none absolute inset-y-0 left-0 hidden w-[52%] bg-gradient-to-r from-background via-background/80 to-transparent lg:block" />
        </div>

        <div className="relative z-10 mt-auto grid grid-cols-2 gap-x-6 gap-y-5 border-t pt-6 sm:grid-cols-5 lg:pointer-events-auto lg:mt-10">
          {[
            [p?.nodes, "Nodes", 0],
            [p?.relationships, "Relationships", 0],
            [p?.counts.Account, "Customer accounts", 0],
            [p?.counts.Ticket, "Support tickets", 0],
            [p?.ms, "ms to read these numbers", 1],
          ].map(([v, label, decimals]) => (
            <div key={label as string}>
              <p className="text-[26px] font-semibold tracking-[-0.6px]">
                {typeof v === "number" ? <CountUp value={v} decimals={decimals as number} /> : <span className="text-ash">—</span>}
              </p>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">{label}</p>
            </div>
          ))}
        </div>
      </div>

      {data ? (
        <div className="pointer-events-none absolute bottom-[124px] right-8 z-10 hidden flex-col items-end gap-1.5 lg:flex">
          <div className="flex gap-3 rounded-full border bg-card/90 px-3 py-1.5 text-[11.5px] text-muted-foreground shadow-panel backdrop-blur">
            {LEGEND.map(([label, color]) => (
              <span key={label} className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
          <p className="text-[11.5px] text-muted-foreground">
            {data.nodes.length} real nodes and {data.edges.length} relationships from Cheerio&apos;s graph
          </p>
        </div>
      ) : null}
    </section>
  );
}
