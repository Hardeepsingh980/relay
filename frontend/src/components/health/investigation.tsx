"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useSWRConfig } from "swr";
import {
  ArrowRight,
  Check,
  ChevronDown,
  CircleAlert,
  CircleDashed,
  Code2,
  Library,
  LoaderCircle,
  Send,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { CaseGraph, CaseLegend } from "@/components/health/case-graph";
import { ActionStatusChip, ModeBadge, Sparkbars } from "@/components/health/bits";
import { Card, isDemoNote, plain } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type {
  CaseEdge,
  CaseNode,
  Evidence,
  FollowUpAnswer,
  PlanAction,
  Step,
  StreamEvent,
  Verdict,
  VerdictStep,
} from "@/lib/relay";
import { useStream } from "@/lib/use-stream";
import { cn } from "@/lib/utils";

interface State {
  status: "running" | "completed" | "failed";
  mode: string;
  modeDetail: string;
  order: string[];
  steps: Record<string, Step>;
  nodes: CaseNode[];
  edges: CaseEdge[];
  evidence: Record<string, Evidence>;
  causal: { nodeIds: string[]; edgeIds: string[] };
  verdict: Verdict | null;
  actions: Record<string, PlanAction>;
  actionOrder: string[];
  followups: FollowUpAnswer[];
  pending: string | null;
  focus: string[] | null;
  error: string | null;
}

const EMPTY: State = {
  status: "running",
  mode: "guided",
  modeDetail: "",
  order: [],
  steps: {},
  nodes: [],
  edges: [],
  evidence: {},
  causal: { nodeIds: [], edgeIds: [] },
  verdict: null,
  actions: {},
  actionOrder: [],
  followups: [],
  pending: null,
  focus: null,
  error: null,
};

/* eslint-disable @typescript-eslint/no-explicit-any */
function reduce(s: State, ev: StreamEvent): State {
  const p = ev.payload as any;
  switch (ev.type) {
    case "investigation.started":
      return { ...s, mode: p.mode };
    case "mode.changed":
      return { ...s, mode: p.mode, modeDetail: p.detail };
    case "step.started":
    case "step.completed":
    case "step.failed": {
      const st = p.step as Step;
      return { ...s, order: s.order.includes(st.id) ? s.order : [...s.order, st.id], steps: { ...s.steps, [st.id]: st } };
    }
    case "evidence.added": {
      const ev2 = { ...s.evidence };
      for (const e of p.items as Evidence[]) ev2[e.id] = { ...ev2[e.id], ...e };
      return { ...s, evidence: ev2 };
    }
    case "graph.node.added":
      return s.nodes.some((n) => n.id === p.node.id) ? s : { ...s, nodes: [...s.nodes, p.node] };
    case "graph.edge.added":
      return s.edges.some((e) => e.id === p.edge.id) ? s : { ...s, edges: [...s.edges, p.edge] };
    case "graph.causal":
      return { ...s, causal: { nodeIds: p.nodeIds, edgeIds: p.edgeIds } };
    case "graph.focus":
      return { ...s, focus: p.nodeIds };
    case "verdict.updated":
      return { ...s, verdict: p.verdict };
    case "followup.started":
      return { ...s, pending: p.question };
    case "followup.completed":
      return { ...s, pending: null, followups: [...s.followups, p.followup] };
    case "investigation.completed":
      return { ...s, status: "completed" };
    case "investigation.failed":
      return { ...s, status: "failed", error: p.error };
    default:
      if (ev.type.startsWith("action.")) {
        const a = p.action as PlanAction;
        return { ...s, actions: { ...s.actions, [a.id]: a }, actionOrder: s.actionOrder.includes(a.id) ? s.actionOrder : [...s.actionOrder, a.id] };
      }
      return s;
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

const FOLLOW_UPS = ["Who else is hit by this bug?", "What changed in the last 90 days?", "Which bug puts the most yearly revenue at risk?", "Who can fix this?"];

export function InvestigationView({ id, onDone, onStatus }: { id: string; onDone?: () => void; onStatus?: (s: State["status"]) => void }) {
  const [s] = useStream<State>(`/api/investigations/${id}/events`, reduce, EMPTY);
  useEffect(() => {
    onStatus?.(s.status);
  }, [s.status, onStatus]);
  const [selected, setSelected] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const steps = s.order.map((k) => s.steps[k]);
  const running = s.status === "running";
  const doneSteps = steps.filter((x) => x.status === "completed").length;
  const ms = steps.reduce((a, b) => a + (b.ms ?? 0), 0);
  const queries = steps.reduce((a, b) => a + b.queries.length, 0);
  const open = (eid: string) => setEvidenceId(eid);

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b px-5 py-3">
          <span className={cn("flex size-8 items-center justify-center rounded-full", running ? "bg-brand-soft text-primary" : "bg-covered-soft text-covered")}>
            {running ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Check className="size-4" aria-hidden />}
          </span>
          <div className="min-w-[280px] flex-1">
            <p className="font-semibold leading-tight">{running ? "Investigating…" : s.status === "failed" ? "Investigation failed" : "Investigation complete"}</p>
            <p className="text-[12.5px] text-muted-foreground">
              {s.mode === "gemini" ? "Gemini picks the steps (via MCP)" : "Standard plan"} · {doneSteps} {doneSteps === 1 ? "check" : "checks"} · {queries} graph {queries === 1 ? "query" : "queries"} · {ms} ms in the graph
              {s.modeDetail ? ` · ${s.modeDetail}` : ""}
            </p>
          </div>
          <CaseLegend />
        </div>
        <div className="grid lg:grid-cols-[340px_minmax(0,1fr)]">
          <ol className="max-h-[560px] space-y-1 overflow-y-auto border-b p-3 lg:border-b-0 lg:border-r" aria-label="Investigation steps" aria-live="polite">
            {steps.map((st) => (
              <StepRow key={st.id} step={st} />
            ))}
            {running && !steps.length ? <li className="px-2 py-3 text-[13px] text-muted-foreground">Starting the investigation…</li> : null}
          </ol>
          <div className="relative min-h-[420px] bg-background/60 lg:min-h-[560px]">
            <CaseGraph
              nodes={s.nodes}
              edges={s.edges}
              causal={s.causal}
              focus={s.focus}
              selectedId={selected}
              onSelect={(nid) => {
                setSelected(nid);
                if (nid && s.evidence[nid]) open(nid);
              }}
              className="absolute inset-0"
            />
            <p className="pointer-events-none absolute bottom-3 left-4 text-[11px] text-muted-foreground">
              {s.nodes.length} items · {s.edges.length} links · click an item to see its source record
            </p>
          </div>
        </div>
      </Card>

      {s.error ? (
        <Card className="flex items-center gap-2 p-4 text-risk">
          <CircleAlert className="size-4" /> {s.error}
        </Card>
      ) : null}
      {s.verdict ? <VerdictCard v={s.verdict} openEvidence={open} evidence={s.evidence} /> : null}
      {s.actionOrder.length ? <SavePlan id={id} actions={s.actionOrder.map((k) => s.actions[k])} onApproved={onDone} /> : null}
      {s.status === "completed" ? <FollowUps id={id} items={s.followups} pending={s.pending} openEvidence={open} /> : null}
      <EvidenceSheet ev={evidenceId ? s.evidence[evidenceId] ?? null : null} onClose={() => setEvidenceId(null)} />
    </div>
  );
}

function StepRow({ step }: { step: Step }) {
  const [show, setShow] = useState(false);
  const icon =
    step.status === "running" ? (
      <LoaderCircle className="size-3.5 animate-spin text-primary" aria-hidden />
    ) : step.status === "failed" ? (
      <TriangleAlert className="size-3.5 text-risk" aria-hidden />
    ) : (
      <Check className="size-3.5 text-covered" aria-hidden />
    );
  return (
    <li className="rounded-xl px-2 py-2 hover:bg-secondary/50">
      <div className="flex items-start gap-2">
        <span className="mt-1">{icon}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-medium leading-snug">{step.title}</p>
          {step.summary ? <p className="mt-0.5 text-[12.5px] leading-snug text-muted-foreground">{plain(step.summary)}</p> : null}
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="font-mono">{step.tool}</span>
            {step.via === "mcp" ? <span className="rounded bg-secondary px-1">via MCP</span> : null}
            {step.ms !== null ? <span className="tabular">{step.ms} ms</span> : null}
            {step.queries.length ? (
              <button type="button" onClick={() => setShow((v) => !v)} className="inline-flex items-center gap-0.5 hover:text-foreground" title="Show the graph query (Cypher)">
                <Code2 className="size-3" aria-hidden /> {show ? "Hide" : "Show"} Cypher ({step.queries.length})
              </button>
            ) : null}
          </div>
          {show ? (
            <div className="mt-2 space-y-2">
              {step.queries.map((q, i) => (
                <div key={i} className="rounded-xl bg-background p-2">
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-snug">{q.cypher}</pre>
                  <p className="mt-1 text-[10.5px] text-muted-foreground">
                    {q.rows} rows · {q.ms} ms{q.params && Object.keys(q.params).length ? ` · inputs ${JSON.stringify(q.params).slice(0, 140)}` : ""}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function EvidencePills({ ids, evidence, open }: { ids: string[]; evidence: Record<string, Evidence>; open: (id: string) => void }) {
  return (
    <span className="inline-flex flex-wrap gap-1 align-middle">
      {ids.map((eid) => {
        const e = evidence[eid];
        return (
          <button
            key={eid}
            type="button"
            onClick={() => open(eid)}
            className="inline-flex max-w-[14rem] items-center gap-1 rounded-full border bg-card px-2 py-0.5 text-[11.5px] text-foreground/80 hover:border-foreground/25"
            title={e ? `${e.sourceSystem}: ${e.title}` : eid}
          >
            <Library className="size-3 text-muted-foreground" aria-hidden />
            <span className="truncate">{e ? `${e.sourceSystem} · ${e.recordId ?? e.title}` : eid}</span>
          </button>
        );
      })}
    </span>
  );
}

function ChainStep({ st, evidence, open }: { st: VerdictStep; evidence: Record<string, Evidence>; open: (id: string) => void }) {
  return (
    <li className="flex gap-3">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-[12px] font-semibold text-background tabular">{st.n}</span>
      <div className="min-w-0 flex-1 pb-1">
        <p className="flex flex-wrap items-center gap-2 font-medium leading-snug">
          {st.title}
          <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", st.kind === "observed" ? "bg-secondary text-muted-foreground" : "border text-muted-foreground")}>
            {st.kind === "observed" ? "From records" : "Inferred"}
            {st.confidence ? ` · ${st.confidence.toFixed(2)} confidence` : ""}
          </span>
        </p>
        <p className="mt-0.5 text-[13.5px] text-muted-foreground">{plain(st.detail)}</p>
        <div className="mt-1.5">
          <EvidencePills ids={st.evidenceIds} evidence={evidence} open={open} />
        </div>
      </div>
    </li>
  );
}

function VerdictCard({ v, evidence, openEvidence }: { v: Verdict; evidence: Record<string, Evidence>; openEvidence: (id: string) => void }) {
  const caveats = v.caveats.filter((c) => !isDemoNote(c)).map(plain);
  return (
    <Card className="overflow-hidden">
      <div className="border-b px-5 py-5 sm:px-6">
        <p className="text-[13px] font-medium text-muted-foreground">
          Relay&apos;s finding · {v.narrativeSource === "template" ? "from the graph" : `written by ${v.narrativeSource}`}
        </p>
        <h2 className="mt-1 text-[22px] font-semibold leading-snug tracking-[-0.2px]">{v.headline}</h2>
        <ol className="mt-3 space-y-1.5 text-[15px] leading-relaxed">
          {v.story.map((line, i) => (
            <li key={i}>{plain(line)}</li>
          ))}
        </ol>
        <div className="mt-4 flex flex-wrap gap-2 text-[12.5px]">
          <span className="rounded-full border px-2.5 py-1 font-medium tabular">
            <span className="text-risk">{v.risk}%</span> {plain(v.riskLabel)}
          </span>
          <span className="rounded-full border px-2.5 py-1 tabular">HubSpot health {v.crmHealthScore}</span>
          <span className="rounded-full border px-2.5 py-1 tabular">
            {v.arrLabel} ARR · renews in {v.renewalInDays} days
          </span>
        </div>
      </div>
      <div className="grid gap-8 px-5 py-5 sm:px-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div>
          <h3 className="text-[15px] font-semibold">How it connects</h3>
          <ol className="mt-3 space-y-4">
            {v.chain.map((st) => (
              <ChainStep key={st.n} st={st} evidence={evidence} open={openEvidence} />
            ))}
          </ol>
          {v.supporting.length ? (
            <>
              <h3 className="mt-6 text-[15px] font-semibold">Other warning signs</h3>
              <ul className="mt-2 space-y-3">
                {v.supporting.map((st, i) => (
                  <li key={i} className="rounded-xl border p-3">
                    <p className="font-medium leading-snug">{st.title}</p>
                    <p className="mt-0.5 text-[13px] text-muted-foreground">{plain(st.detail)}</p>
                    <div className="mt-1.5">
                      <EvidencePills ids={st.evidenceIds} evidence={evidence} open={openEvidence} />
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
        <div className="space-y-5">
          {v.blastRadius ? (
            <div className="rounded-xl border p-4">
              <p className="text-[12.5px] font-medium text-muted-foreground">Other accounts hit · {v.bugId}</p>
              <p className="mt-1 text-[26px] font-semibold tabular">+{v.blastRadius.arrLabel} ARR</p>
              <p className="text-[13px] text-muted-foreground">
                in {v.blastRadius.accounts} more accounts with the same bug: {v.blastRadius.names.join(", ")}
              </p>
            </div>
          ) : null}
          {v.playbook ? (
            <div className="rounded-xl border p-4">
              <p className="text-[12.5px] font-medium text-muted-foreground">What worked before · {v.playbook.name}</p>
              <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-[13.5px]">
                {v.playbook.steps.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ol>
              <p className="mt-2 text-[12px] text-muted-foreground">
                {v.playbook.outcome}
                {v.playbook.workedFor.length ? ` · worked for ${v.playbook.workedFor.join(", ")}` : ""}
              </p>
            </div>
          ) : null}
          {v.memory ? (
            <div className="rounded-xl border p-4 text-[13px]">
              <p className="font-medium">Last investigated on {v.memory.at}</p>
              <p className="mt-0.5 text-muted-foreground">{v.memory.verdict}</p>
            </div>
          ) : null}
          {v.counterEvidence.length ? (
            <div>
              <h3 className="text-[15px] font-semibold">Good signs</h3>
              <ul className="mt-2 space-y-2">
                {v.counterEvidence.map((c) => (
                  <li key={c.title} className="rounded-xl border p-3 text-[13px]">
                    <p className="flex items-center gap-2 font-medium">
                      <span className="size-1.5 shrink-0 rounded-full bg-covered" aria-hidden />
                      {c.title}
                    </p>
                    <p className="text-muted-foreground">{c.detail}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {caveats.length ? (
            <div>
              <h3 className="text-[15px] font-semibold">Keep in mind</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[12.5px] text-muted-foreground">
                {caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function SavePlan({ id, actions, onApproved }: { id: string; actions: PlanAction[]; onApproved?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const pending = actions.filter((a) => ["proposed", "failed", "needs_attention"].includes(a.status));
  const approve = async (ids: string[]) => {
    setBusy(true);
    try {
      await api.post(`/api/investigations/${id}/approve`, { actionIds: ids });
      toast.success(ids.length > 1 ? `Approved ${ids.length} steps` : "Approved");
      onApproved?.();
    } catch (e) {
      toast.error("Approval failed", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[18px] font-semibold">Save plan</h2>
          <p className="text-[13.5px] text-muted-foreground">Nothing runs until you approve. Customer emails stay as drafts.</p>
        </div>
        {pending.length ? (
          <Button onClick={() => approve(pending.map((a) => a.id))} disabled={busy}>
            <ShieldCheck className="size-4" /> {busy ? "Running…" : `Approve all ${pending.length}`}
          </Button>
        ) : null}
      </div>
      <ul className="mt-5 space-y-3">
        {actions.map((a) => (
          <li key={a.id} className="rounded-xl border p-4">
            <div className="flex flex-wrap items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {a.title}
                  {a.customerFacing ? <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn">Customer-facing</span> : null}
                </p>
                <p className="text-[13px] text-muted-foreground">
                  {plain(a.summary)} · {a.destination.system} → {a.destination.target}
                </p>
              </div>
              {a.status === "proposed" ? <ModeBadge mode={a.destination.mode} /> : <ActionStatusChip status={a.status} />}
              {["proposed", "failed", "needs_attention"].includes(a.status) ? (
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(editing === a.id ? null : a.id)}>
                    {editing === a.id ? "Close" : "Edit"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => approve([a.id])} disabled={busy}>
                    Approve
                  </Button>
                </div>
              ) : null}
            </div>
            {editing === a.id ? <ActionEditor id={id} action={a} onSaved={() => setEditing(null)} /> : <PayloadPreview a={a} />}
            {a.result ? (
              <p className="mt-2 rounded-xl bg-background px-3 py-2 text-[12.5px]">
                {plain(a.result.message)}
                {a.approvedBy ? <span className="text-muted-foreground"> · approved by {a.approvedBy}</span> : null}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PayloadPreview({ a }: { a: PlanAction }) {
  const p = a.payload as Record<string, string>;
  const text = plain(a.type === "email.draft" ? `Subject: ${p.subject}\n\n${p.body}` : a.type === "slack.post" ? p.message : a.type === "bug.escalate" ? p.comment : `${p.title}\n${p.description ?? ""}`);
  return (
    <details className="mt-2 text-[12.5px]">
      <summary className="inline-flex cursor-pointer items-center gap-1 text-muted-foreground hover:text-foreground">
        <ChevronDown className="size-3.5" aria-hidden /> Preview text
      </summary>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-background p-3 font-sans text-[13px] leading-relaxed">{text}</pre>
    </details>
  );
}

function ActionEditor({ id, action, onSaved }: { id: string; action: PlanAction; onSaved: () => void }) {
  const p = action.payload as Record<string, string>;
  const fields = action.type === "email.draft" ? ["subject", "body"] : action.type === "slack.post" ? ["message"] : action.type === "bug.escalate" ? ["proposedPriority", "comment"] : ["title", "description"];
  const [vals, setVals] = useState<Record<string, string>>(Object.fromEntries(fields.map((f) => [f, String(p[f] ?? "")])));
  const save = async () => {
    try {
      await api.patch(`/api/investigations/${id}/actions/${action.id}`, { payload: vals });
      toast.success("Saved");
      onSaved();
    } catch (e) {
      toast.error("Save failed", { description: e instanceof Error ? e.message : undefined });
    }
  };
  return (
    <div className="mt-3 space-y-2">
      {fields.map((f) =>
        f === "proposedPriority" ? (
          <label key={f} className="flex items-center gap-2 text-[13px]">
            Priority
            <select value={vals[f]} onChange={(e) => setVals({ ...vals, [f]: e.target.value })} className="rounded-md border bg-card px-2 py-1">
              {["P1", "P2", "P3", "P4"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        ) : f === "subject" || f === "title" ? (
          <Input key={f} value={vals[f]} onChange={(e) => setVals({ ...vals, [f]: e.target.value })} aria-label={f} />
        ) : (
          <Textarea key={f} value={vals[f]} onChange={(e) => setVals({ ...vals, [f]: e.target.value })} rows={6} aria-label={f} />
        ),
      )}
      <Button size="sm" onClick={save}>
        Save changes
      </Button>
    </div>
  );
}

function FollowUps({ id, items, pending, openEvidence }: { id: string; items: FollowUpAnswer[]; pending: string | null; openEvidence: (id: string) => void }) {
  const [q, setQ] = useState("");
  const { mutate } = useSWRConfig();
  const ask = async (question: string) => {
    if (!question.trim()) return;
    setQ("");
    try {
      await api.post(`/api/investigations/${id}/followups`, { question });
      mutate((k) => typeof k === "string" && k.startsWith("/api/accounts"));
    } catch (e) {
      toast.error("Follow-up failed", { description: e instanceof Error ? e.message : undefined });
    }
  };
  const asked = new Set(items.map((i) => i.question));
  return (
    <Card className="p-5">
      <h2 className="text-[18px] font-semibold">Ask a follow-up</h2>
      <p className="text-[13.5px] text-muted-foreground">Answers come from the same graph.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {FOLLOW_UPS.filter((f) => !asked.has(f)).map((f) => (
          <button key={f} type="button" onClick={() => ask(f)} className="rounded-full border px-3 py-1 text-[13px] hover:bg-secondary" disabled={!!pending}>
            {f}
          </button>
        ))}
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example, who else is hit by CHEER-2547?" aria-label="Follow-up question" />
        <Button type="submit" disabled={!!pending || !q.trim()}>
          <Send className="size-4" /> Ask
        </Button>
      </form>
      <ul className="mt-5 space-y-4">
        {pending ? (
          <li className="flex items-center gap-2 text-[13.5px] text-muted-foreground">
            <CircleDashed className="size-4 animate-spin" aria-hidden /> {pending}
          </li>
        ) : null}
        {[...items].reverse().map((f) => (
          <li key={f.id} className="rounded-xl border p-4">
            <p className="text-[12.5px] font-medium text-muted-foreground">{f.question}</p>
            <p className="mt-1 text-[15px]">{f.answer}</p>
            {f.observed.length ? (
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[13px] text-muted-foreground">
                {f.observed.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            ) : null}
            {f.inferred.length ? <p className="mt-2 text-[12px] text-muted-foreground">{f.inferred.join(" ")}</p> : null}
            {f.evidenceIds.length ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {f.evidenceIds.slice(0, 6).map((eid) => (
                  <button key={eid} type="button" onClick={() => openEvidence(eid)} className="rounded-full border bg-card px-2 py-0.5 text-[11.5px] hover:border-foreground/25">
                    {eid}
                  </button>
                ))}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function EvidenceSheet({ ev, onClose }: { ev: Evidence | null; onClose: () => void }) {
  const fields = useMemo(() => (ev?.fields ?? []).filter(([, v]) => v !== null && v !== undefined && v !== ""), [ev]);
  return (
    <Sheet open={!!ev} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[480px]">
        <SheetHeader className="border-b px-5 py-4">
          <p className="text-xs font-medium text-muted-foreground">{ev?.sourceSystem}</p>
          <SheetTitle className="pr-8 text-[16px] leading-snug">{ev?.title}</SheetTitle>
          <SheetDescription className="text-xs">
            {ev?.recordId}
            {ev?.date ? ` · ${ev.date}` : ""}
          </SheetDescription>
        </SheetHeader>
        {ev ? (
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4 text-[14px]">
            {ev.quote ? <blockquote className="rounded-xl border-l-2 border-foreground/30 bg-background px-3 py-2 leading-relaxed">{ev.quote}</blockquote> : null}
            {ev.series ? <Sparkbars series={ev.series} /> : null}
            {fields.length ? (
              <dl className="divide-y rounded-xl border">
                {fields.map(([k, v]) => (
                  <div key={k} className="flex gap-3 px-3 py-2 text-[13px]">
                    <dt className="w-40 shrink-0 text-muted-foreground">{plain(k)}</dt>
                    <dd className="min-w-0 break-words">{plain(String(v))}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {ev.relationship ? (
              <p className="flex items-start gap-1.5 text-[12.5px] text-muted-foreground">
                <ArrowRight className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {ev.relationship}
              </p>
            ) : null}
            {ev.note && !isDemoNote(ev.note) ? <p className="text-[12.5px] text-muted-foreground">{plain(ev.note)}</p> : null}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
