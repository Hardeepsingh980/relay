"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowRight, Building2, CircleCheck, Loader2, TriangleAlert } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { ActionsPanel, DocProposals } from "@/components/relay/actions-panel";
import { CoverageBar } from "@/components/relay/coverage-bar";
import { GraphLegend, KnowledgeGraph, RelationshipList } from "@/components/relay/knowledge-graph";
import { Avatar, Card, Skeleton, TYPE_META, TypeIcon, formatDay } from "@/components/relay/primitives";
import { RiskCard } from "@/components/relay/risk-card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api, enc } from "@/lib/api";
import type { BatonEvent, GraphView, Handover, ItemType, RiskItem } from "@/lib/types";
import { useEvents } from "@/lib/use-events";
import { cn } from "@/lib/utils";

const ORDER: ItemType[] = ["System", "Account", "Decision", "Workaround"];

export function HandoverClient({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const search = useSearchParams();
  const { persona } = useApp();
  const { data, mutate } = useSWR<Handover>(`/api/handovers/${id}`);
  const { data: graph, mutate: mutateGraph } = useSWR<GraphView>(data?.handover.analyzedAt ? `/api/handovers/${id}/graph` : null);
  const { data: impact, mutate: mutateImpact } = useSWR<ImpactRow[]>(`/api/handovers/${id}/customer-impact`);
  const first = data?.leaver.name.split(" ")[0] ?? "";
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const [streamed, setStreamed] = useState<RiskItem[]>([]);
  const [departed, setDeparted] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [version, setVersion] = useState("0");
  const [delta, setDelta] = useState<number | null>(null);
  const started = useRef(false);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const prevAtRisk = useRef<number | null>(null);

  // Start the analysis once when arriving from "Start handover", or reattach to a running one.
  useEffect(() => {
    if (!data || started.current) return;
    const h = data.handover;
    if (h.status === "analyzing" && h.analyses) {
      started.current = true;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAnalysisId(`an-${h.id}-${h.analyses}`);
    } else if (h.status === "created" && search.get("analyze") === "1") {
      started.current = true;
      api.post<{ analysisId: string }>(`/api/handovers/${h.id}/analyze`).then((r) => setAnalysisId(r.analysisId));
    }
  }, [data, search]);

  useEvents(analysisId ? `/api/analyses/${enc(analysisId)}/events` : null, (ev: BatonEvent) => {
    if (ev.type === "analysis.step") setSteps((s) => [...s, String(ev.payload.label)]);
    if (ev.type === "risk.detected") {
      const r = ev.payload.riskItem as RiskItem;
      setStreamed((s) => (s.some((x) => x.id === r.id) ? s : [...s, r]));
    }
    if (ev.type === "analysis.completed") {
      mutate().then(() => {
        mutateGraph();
        setStreamed([]);
        setAnalysisId(null);
      });
    }
    if (ev.type === "analysis.failed") toast.error("Analysis failed", { description: String(ev.payload.error) });
    if (ev.type === "account.risk.updated") {
      mutateImpact();
      const p = ev.payload as { name: string; before: number; after: number };
      toast(`${p.name}: risk ${p.before}% → ${p.after}%`, { description: `Account Health saw in the graph that ${first} is leaving.` });
    }
  });

  // Live updates from other personas (Rahul answering, verifications).
  useEvents(data?.handover.analyzedAt ? `/api/handovers/${enc(id)}/events` : null, (ev) => {
    if (ev.type === "coverage.updated") return;
    mutate();
    mutateGraph();
    setVersion(ev.eventId);
  });

  useEffect(() => {
    if (!data) return;
    const now = data.coverage.atRisk;
    if (prevAtRisk.current !== null && now < prevAtRisk.current) {
      setDelta(now - prevAtRisk.current);
      const t = setTimeout(() => setDelta(null), 2400);
      prevAtRisk.current = now;
      return () => clearTimeout(t);
    }
    prevAtRisk.current = now;
  }, [data]);

  const items = useMemo(() => (analysisId ? streamed : data?.riskItems ?? []), [analysisId, streamed, data]);
  const canManage = !!data && persona === data.handover.managerId;

  const act = useCallback(
    async (fn: () => Promise<unknown>, ok?: string) => {
      try {
        await fn();
        await mutate();
        mutateGraph();
        setVersion(String(Date.now()));
        if (ok) toast.success(ok);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Something went wrong. Try again.");
      }
    },
    [mutate, mutateGraph],
  );

  const select = (itemId: string | null) => {
    setSelected(itemId);
    if (itemId) cardRefs.current[itemId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  if (!data) {
    return (
      <div className="mx-auto max-w-[1180px] px-8 py-10">
        <Skeleton className="h-24" />
        <Skeleton className="mt-6 h-[480px]" />
      </div>
    );
  }
  const h = data.handover;
  const analyzing = !!analysisId || h.status === "analyzing";
  const total = analyzing ? streamed.length : data.coverage.total;
  const atRisk = analyzing ? streamed.length : data.coverage.atRisk;
  const counts = Object.fromEntries(ORDER.map((t) => [t, items.filter((r) => r.type === t).length]));

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-10 md:px-8">
      <header className="flex flex-wrap items-center gap-4">
        <Avatar name={data.leaver.name} size={48} ring={departed ? "risk" : undefined} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-muted-foreground">Handover</p>
          <h1 className="mt-1 text-[30px] font-semibold leading-tight tracking-[-0.3px] md:text-[34px] md:tracking-[-0.4px]">{data.leaver.name}</h1>
          <p className="mt-1 text-[15px] text-muted-foreground">
            {data.leaver.role} · {data.leaver.team} · Last day {formatDay(h.lastDay, { weekday: "short", day: "numeric", month: "short" })}
            {data.joiner ? <> · {data.joiner.name.split(" ")[0]} takes over</> : null}
          </p>
        </div>
        <div className="text-right" aria-live="polite" aria-atomic="true">
          <div className="flex items-baseline justify-end gap-2">
            {delta ? <span className="text-sm font-medium text-covered tabular animate-in fade-in slide-in-from-bottom-1">{delta}</span> : null}
            <span className={cn("text-[44px] font-semibold leading-none tracking-[-0.4px] tabular transition-colors duration-300", atRisk === 0 && total > 0 ? "text-covered" : atRisk > 0 && "text-risk")}>
              {atRisk}
            </span>
          </div>
          <p className="text-sm text-muted-foreground">{atRisk === 0 && total > 0 ? "nothing left at risk" : "at risk"}</p>
        </div>
      </header>

      {!analyzing && data.coverage.total ? <CoverageBar coverage={data.coverage} className="mt-5" legend /> : null}

      {h.status === "created" && !analyzing ? (
        <Card className="mt-8 flex flex-col items-start gap-3 p-5">
          <p className="font-medium">Ready to analyze</p>
          <p className="text-muted-foreground">Find what only {first} knows before the last day.</p>
          <Button
            onClick={() => {
              started.current = true;
              api.post<{ analysisId: string }>(`/api/handovers/${h.id}/analyze`).then((r) => setAnalysisId(r.analysisId));
            }}
          >
            Run analysis
          </Button>
        </Card>
      ) : null}

      {analyzing ? (
        <div className="mt-6 space-y-1.5 rounded-2xl border bg-card px-5 py-4" aria-live="polite">
          {steps.map((s, i) => (
            <p key={i} className={cn("flex items-center gap-2 text-sm", i === steps.length - 1 ? "text-foreground" : "text-muted-foreground")}>
              {i === steps.length - 1 ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <CircleCheck className="size-3.5" aria-hidden />}
              {s}
            </p>
          ))}
          {steps.length === 0 ? <p className="text-sm text-muted-foreground">Starting…</p> : null}
        </div>
      ) : null}

      {total > 0 || analyzing ? (
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="order-2 lg:sticky lg:top-16 lg:order-none lg:self-start">
            <Card className="p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-[16px] font-semibold">What leaves with {first}</h2>
                  <p className="text-xs text-muted-foreground">What {first} knows, and who else does</p>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <span className={cn(departed ? "text-foreground" : "text-muted-foreground")}>Preview departure</span>
                  <Switch checked={departed} onCheckedChange={setDeparted} disabled={!graph || analyzing} aria-label="Preview departure" />
                </label>
              </div>
              <div className="relative mt-2 h-[320px] sm:h-[460px]">
                {graph && !analyzing ? (
                  <KnowledgeGraph
                    graph={graph}
                    centerId={data.leaver.id}
                    departed={departed}
                    selectedId={selected}
                    onSelect={select}
                    className="h-full"
                    label={`Graph of the work around ${data.leaver.name}. Only ${first} knows ${data.coverage.total} of these items.`}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    {analyzing ? "Building the graph…" : <Skeleton className="h-full w-full" />}
                  </div>
                )}
              </div>
              <GraphLegend />
              {departed ? (
                <p className="mt-2 text-xs text-muted-foreground">Red items have no one else who knows them well.</p>
              ) : null}
              {graph ? <RelationshipList items={graph.relationships} /> : null}
            </Card>
            {data.thinCoverage.length && !analyzing ? (
              <Card className="mt-4 p-4">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <TriangleAlert className="size-4 text-warn" aria-hidden /> Watch list
                </p>
                <ul className="mt-1 space-y-1 text-sm text-muted-foreground">
                  {data.thinCoverage.map((t) => (
                    <li key={t.id}>
                      {t.title}: <span className="text-foreground tabular">{t.remaining}</span> left who know it
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
          </div>

          <div className="order-1 min-w-0 lg:order-none">
            <div className="mb-5">
              <h2 className="text-heading">
                {analyzing ? `Finding what only ${first} knows…` : `${data.coverage.total} things only ${first} knows`}
              </h2>
              <p className="mt-1 text-[15px] text-muted-foreground tabular">{ORDER.map((t) => `${TYPE_META[t].plural} ${counts[t] ?? 0}`).join(" · ")}</p>
              {impact?.length ? <CustomerImpact rows={impact} first={first} /> : null}
              {!analyzing && canManage ? (
                <BulkBar
                  handover={data}
                  onDone={async (msg) => {
                    await mutate();
                    mutateGraph();
                    setVersion(String(Date.now()));
                    toast.success(msg);
                  }}
                />
              ) : null}
            </div>
            <div className="space-y-6">
              {ORDER.map((t) => {
                const group = items.filter((r) => r.type === t);
                if (!group.length) return null;
                return (
                  <section key={t} aria-label={TYPE_META[t].plural}>
                    <p className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <TypeIcon type={t} className="size-3.5" /> {TYPE_META[t].plural} <span className="tabular">{group.length}</span>
                    </p>
                    <div className="space-y-2">
                      {group.map((r) => (
                        <div key={r.id} className={analyzing ? "animate-in fade-in slide-in-from-bottom-1 duration-300" : undefined}>
                          <RiskCard
                            ref={(el) => {
                              cardRefs.current[r.itemId] = el;
                            }}
                            risk={r}
                            leaverFirst={first}
                            selected={selected === r.itemId}
                            canManage={canManage && !analyzing}
                            onSelect={() => setSelected(r.itemId)}
                            onAssign={(pid) => act(() => api.post(`/api/handovers/${h.id}/risks/${enc(r.id)}/assign`, { successorId: pid, managerApproval: true }), "Next owner assigned")}
                            onDismiss={(reason) => act(() => api.post(`/api/handovers/${h.id}/risks/${enc(r.id)}/dismiss`, { reason }), "Dismissed")}
                            onRestore={() => act(() => api.post(`/api/handovers/${h.id}/risks/${enc(r.id)}/restore`))}
                            onVerify={() => act(() => api.post(`/api/handovers/${h.id}/risks/${enc(r.id)}/verify`), "Verified. The next owner now knows this.")}
                          />
                        </div>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>

            {!analyzing && data.coverage.total ? (
              <div className="mt-10 space-y-8">
                <InterviewStatus handover={data} />
                <DocProposals handoverId={h.id} canManage={canManage} version={version} />
                <ActionsPanel handoverId={h.id} canManage={canManage} version={version} />
                <CloseHandover handover={data} canManage={canManage} onClosed={() => mutate()} />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

interface ImpactRow {
  id: string;
  name: string;
  before: number | null;
  after: number;
  detail: string;
  open: boolean;
  arr: number;
}

function CustomerImpact({ rows, first }: { rows: ImpactRow[]; first: string }) {
  return (
    <Card className="mt-4 p-4">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Building2 className="size-4 text-muted-foreground" aria-hidden /> Customer impact
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">Customers who depend on {first}, rescored</p>
      <ul className="mt-2 divide-y">
        {rows.map((r) => (
          <li key={r.id}>
            <Link href={`/accounts/${r.id}`} className="-mx-2 flex items-center gap-2 rounded-xl px-2 py-2 text-sm transition-colors hover:bg-background">
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{r.name}</span>
                <span className="block truncate text-xs text-muted-foreground">{r.detail}</span>
              </span>
              <span className="text-right tabular">
                <span className="text-muted-foreground">{r.before ?? "—"}%</span> → <b className={r.after >= 60 ? "text-risk" : ""}>{r.after}%</b>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function BulkBar({ handover, onDone }: { handover: Handover; onDone: (msg: string) => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const unassigned = handover.riskItems.filter((r) => !r.successor && r.suggestions.length && r.state !== "dismissed").length;
  const captured = handover.riskItems.filter((r) => r.state === "captured" && r.successor).length;
  if (!unassigned && !captured) return null;
  const run = async (key: string, path: string, msg: (n: number) => string, field: "assigned" | "verified") => {
    setBusy(key);
    try {
      const r = await api.post<Record<string, number>>(`/api/handovers/${handover.handover.id}/${path}`);
      await onDone(msg(r[field]));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border bg-card px-4 py-3">
      <p className="mr-auto text-[14px] text-foreground/80">
        {unassigned ? `${unassigned} item${unassigned === 1 ? " still needs" : "s still need"} a next owner.` : `${captured} answer${captured === 1 ? " is" : "s are"} ready to verify.`}
      </p>
      {unassigned ? (
        <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("assign", "accept-suggestions", (n) => `Assigned ${n} next owners`, "assigned")}>
          {busy === "assign" ? <Loader2 className="animate-spin" /> : null} Accept all suggestions
        </Button>
      ) : null}
      {captured ? (
        <Button size="sm" disabled={!!busy} onClick={() => run("verify", "verify-captured", (n) => `Verified ${n} answers`, "verified")}>
          {busy === "verify" ? <Loader2 className="animate-spin" /> : <CircleCheck />} Verify all answers ({captured})
        </Button>
      ) : null}
    </div>
  );
}

function InterviewStatus({ handover }: { handover: Handover }) {
  const captured = handover.riskItems.filter((r) => r.knowledge).length;
  const first = handover.leaver.name.split(" ")[0];
  const open = handover.riskItems.filter((r) => r.state !== "dismissed").length;
  return (
    <Card className="flex flex-wrap items-center gap-4 p-4">
      <div className="flex-1">
        <p className="font-medium">{first}&apos;s handover questions</p>
        <p className="text-sm text-muted-foreground">
          {captured === 0 ? `${open} questions for ${first}, under “My handover”.` : `${captured} of ${open} answered. Verify each with its next owner.`}
        </p>
      </div>
      <Link href="/interview" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
        Preview questions <ArrowRight className="size-3.5" />
      </Link>
    </Card>
  );
}

function CloseHandover({ handover, canManage, onClosed }: { handover: Handover; canManage: boolean; onClosed: () => void }) {
  const c = handover.coverage;
  if (handover.handover.status === "closed") {
    return <p className="text-sm text-covered">Handover closed. Every item was verified or dismissed with a reason.</p>;
  }
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-6">
      <p className="text-sm text-muted-foreground">
        {c.complete ? "Everything is verified or dismissed." : `${c.atRisk} of ${c.total} items still open.`}
      </p>
      <Button
        variant="outline"
        disabled={!c.complete || !canManage}
        onClick={async () => {
          await api.post(`/api/handovers/${handover.handover.id}/close`);
          toast.success("Handover closed");
          onClosed();
        }}
      >
        Close handover
      </Button>
    </div>
  );
}
