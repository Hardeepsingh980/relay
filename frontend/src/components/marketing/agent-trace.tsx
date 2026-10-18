"use client";

import { useEffect, useMemo, useState } from "react";

import { typeColor } from "@/components/marketing/hero-graph";
import { AGENT_COLOR, useLanding } from "@/components/marketing/landing-hero";
import { useInView } from "@/components/marketing/motion";
import type { LandingGraph } from "@/lib/api";
import { cn } from "@/lib/utils";

// The Cypher each agent runs for its finding. They return the same paths the landing graph lights up.
const CYPHER: Record<string, string> = {
  "Account Health": `MATCH (a:Account {name: 'Northwind Foods'})
      <-[:WORKS_AT]-(old:Contact {active: false})
MATCH (new:Contact)-[:SUCCEEDED]->(old)
MATCH (new)-[:RAISED]->(t:Ticket)
      -[:SYMPTOM_OF]->(b:Bug)-[:AFFECTS]->(f:Feature)
RETURN old, new, collect(t), b, f`,
  Handovers: `MATCH (p:Person {name: 'Rahul Verma'})-[k:KNOWS]->(x)
WHERE k.score > 0.6 AND (x:System OR x:Account)
RETURN x.name, k.score
ORDER BY k.score DESC`,
  "Sales Assist": `MATCH (m:Person)-[:MADE]->(p:Promise)
      -[:TO]->(a:Account {name: 'Northwind Foods'})
MATCH (p)-[:DEPENDS_ON]->(r:RoadmapItem)
RETURN m.name, p.text, p.due, r.etaLabel`,
};

const VERB: Record<string, string> = {
  WORKS_AT: "works at",
  SUCCEEDED: "took over from",
  RAISED: "raised",
  SYMPTOM_OF: "is a symptom of",
  AFFECTS: "breaks",
  OWNED_BY: "is owned by",
  KNOWS: "knows",
  MADE: "made the promise",
  TO: "was promised to",
  DEPENDS_ON: "depends on",
  CONCERNS: "is about",
  USES: "uses",
  ABOUT_FEATURE: "is about",
  DEPENDS_ON_SYSTEM: "depends on",
};

const TYPE_NAME: Record<string, string> = { RoadmapItem: "Roadmap", Bug: "Bug", Ticket: "Support ticket" };

type Node = LandingGraph["nodes"][number];
interface Step {
  node: Node;
  from?: Node;
  to?: Node;
  rel?: string;
}

function label(n: Node) {
  return n.type === "Bug" && n.key ? n.key : n.name;
}

function steps(data: LandingGraph | undefined, i: number): Step[] {
  const story = data?.stories[i];
  if (!data || !story) return [];
  const by = new Map(data.nodes.map((n) => [n.id, n]));
  const rel = new Map(data.edges.map((e) => [`${e.s}>${e.t}`, e.type]));
  return story.path.map((id, k) => {
    const node = by.get(id)!;
    for (let j = k - 1; j >= 0; j--) {
      const prev = story.path[j];
      const out = rel.get(`${prev}>${id}`);
      if (out) return { node, from: by.get(prev), to: node, rel: out };
      const back = rel.get(`${id}>${prev}`);
      if (back) return { node, from: node, to: by.get(prev), rel: back };
    }
    return { node };
  });
}

export function AgentTrace() {
  const { data } = useLanding();
  const [tab, setTab] = useState(0);
  const [ref, inView] = useInView<HTMLDivElement>(0.25);
  const list = useMemo(() => steps(data, tab), [data, tab]);
  const story = data?.stories[tab];
  const agents = data?.stories.map((s) => s.agent) ?? Object.keys(CYPHER);

  return (
    <section id="trace" className="scroll-mt-20 px-3 py-6 md:px-6">
      <div
        ref={ref}
        className="relative isolate mx-auto max-w-[1240px] overflow-hidden rounded-[28px] border bg-card px-5 py-14 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_16px_48px_rgba(15,23,42,0.06)] md:px-12 md:py-16"
      >
        <div aria-hidden className="paper-dots absolute inset-0 -z-10 [mask-image:linear-gradient(to_bottom,black,transparent_60%)]" />

        <div className="grid gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div>
            <p className="text-[13px] font-medium text-primary">How an agent finds things</p>
            <h2 className="mt-2 text-[34px] font-semibold leading-[1.1] tracking-[-0.8px] sm:text-[40px]">
              No guesses. A path you can check.
            </h2>
            <p className="mt-4 max-w-[460px] text-[16px] leading-relaxed text-muted-foreground">
              Each finding is a walk through the graph. Every hop is a real record: a contact, a ticket, a bug, a promise.
              Pick an agent and watch its path.
            </p>
            <div className="mt-7 flex flex-wrap gap-2" role="tablist" aria-label="Agents">
              {agents.map((a, i) => (
                <button
                  key={a}
                  role="tab"
                  aria-selected={tab === i}
                  onClick={() => setTab(i)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[13.5px] font-medium transition",
                    tab === i ? "border-foreground/15 bg-card text-foreground shadow-panel" : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span className="size-2 rounded-full" style={{ background: AGENT_COLOR[a] }} />
                  {a}
                </button>
              ))}
            </div>
            <pre className="mt-6 overflow-x-auto rounded-2xl border bg-background p-4 font-mono text-[12.5px] leading-[1.65] text-[#1f4f8f]">
              <code>{CYPHER[agents[tab]] ?? ""}</code>
            </pre>
            <p className="mt-2 text-[12px] text-muted-foreground">Cypher on FalkorDB. The agents run queries like this one, step by step.</p>
          </div>

          <div>
            <Trace key={tab} steps={list} play={inView} color={AGENT_COLOR[agents[tab]] ?? "#262626"} />
            {story ? (
              <div className="mt-6 rounded-2xl border p-4" style={{ borderColor: `${AGENT_COLOR[story.agent]}40`, background: `${AGENT_COLOR[story.agent]}0d` }}>
                <p className="text-[12px] font-medium" style={{ color: AGENT_COLOR[story.agent] }}>
                  {story.agent} found
                </p>
                <p className="mt-1 text-[17px] font-semibold tracking-[-0.2px]">{story.chip}</p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function Trace({ steps, play, color }: { steps: Step[]; play: boolean; color: string }) {
  const colorOf = (n: Node) => typeColor(n.type);
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!play || !steps.length) return;
    const id = setInterval(() => setShown((n) => (n >= steps.length ? (clearInterval(id), n) : n + 1)), 330);
    return () => clearInterval(id);
  }, [play, steps.length]);

  if (!steps.length) return <div className="h-[420px] animate-pulse rounded-2xl bg-muted" />;
  return (
    <ol className="relative">
      <span aria-hidden className="absolute bottom-4 left-[15px] top-4 w-px bg-border" />
      <span
        aria-hidden
        className="absolute left-[15px] top-4 w-px transition-[height] duration-300 ease-out"
        style={{ height: `calc(${Math.max(0, Math.min(shown, steps.length) - 1) / Math.max(1, steps.length - 1)} * (100% - 2rem))`, background: color }}
      />
      {steps.map((s, i) => {
        const on = i < shown;
        return (
          <li
            key={`${s.node.id}-${i}`}
            className={cn("relative flex gap-4 py-2 transition-all duration-500 ease-out-soft", on ? "translate-x-0 opacity-100" : "translate-x-3 opacity-0")}
          >
            <span
              className="relative z-10 mt-0.5 flex size-[31px] shrink-0 items-center justify-center rounded-full border text-[11.5px] font-semibold tabular"
              style={{ borderColor: on ? colorOf(s.node) : "var(--border)", background: "var(--card)", color: colorOf(s.node), boxShadow: on ? `0 2px 8px ${colorOf(s.node)}33` : "none" }}
            >
              {i}
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-[11px] font-medium uppercase tracking-[0.08em]" style={{ color: colorOf(s.node) }}>
                {TYPE_NAME[s.node.type] ?? s.node.type}
                {s.rel ? <span className="ml-2 rounded bg-muted px-1.5 py-px font-mono text-[10.5px] normal-case tracking-normal text-muted-foreground">{s.rel}</span> : null}
              </p>
              <p className="mt-0.5 text-[14.5px] leading-snug text-foreground/75">
                {s.from && s.to && s.rel ? (
                  <>
                    <b className="font-semibold text-foreground">{label(s.from)}</b> {VERB[s.rel] ?? s.rel.toLowerCase().replaceAll("_", " ")}{" "}
                    <b className="font-semibold text-foreground">{label(s.to)}</b>
                  </>
                ) : (
                  <b className="font-semibold text-foreground">{label(s.node)}</b>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
