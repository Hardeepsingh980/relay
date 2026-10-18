"use client";

import Link from "next/link";
import { use, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { toast } from "sonner";
import { Activity, ArrowLeft, Bot, Bug, CalendarClock, ChevronRight, Code2, DoorOpen, Handshake, History, Search, Users } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { FactorList, HealthVsRisk, ModeBadge, SilentBadge, Sparkbars } from "@/components/health/bits";
import { InvestigationView } from "@/components/health/investigation";
import { Avatar, Card, CardTitle, Dot, EmptyState, PageHeader, Skeleton, formatDay } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { type AccountDetail, type PromiseRow } from "@/lib/relay";
import { cn } from "@/lib/utils";

export function AccountClient({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { session } = useApp();
  const { mutate } = useSWRConfig();
  const { data, error } = useSWR<AccountDetail>(`/api/accounts/${id}`, { refreshInterval: 20_000 });
  const [invId, setInvId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [showQueries, setShowQueries] = useState(false);
  const [invStatus, setInvStatus] = useState<string>("running");

  if (error) return <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8"><EmptyState title="Account not found" body="This account is not in the graph for this workspace." /></div>;
  if (!data) return <AccountSkeleton />;
  const a = data.account;
  const r = data.risk;
  const active = invId ?? (data.investigation?.status === "running" ? data.investigation.id : null);
  const running = !!active && invStatus === "running";
  const llm = session?.llm.enabled;

  const investigate = async (mode: "guided" | "gemini") => {
    setStarting(true);
    try {
      const res = await api.post<{ id: string; modeDetail: string }>(`/api/accounts/${id}/investigate`, { mode });
      setInvStatus("running");
      setInvId(res.id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      toast.error("The investigation did not start", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-8 md:px-8">
      <Link href="/accounts" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Risk Radar
      </Link>
      <div className="mt-3 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div>
          <PageHeader
            eyebrow={`${a.industry} · ${a.plan} plan · ${a.seats} seats · ${a.country === "US" ? "United States" : "India"}`}
            title={
              <>
                {a.name} {r.silent ? <SilentBadge className="text-[12.5px]" /> : null}
              </>
            }
            subtitle={`${r.hint}.`}
          />
          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[13px]">
            <div>
              <dt className="text-muted-foreground">ARR</dt>
              <dd className="font-medium tabular">{a.arrLabel}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Renews</dt>
              <dd className="font-medium tabular">
                {formatDay(a.renewalDate, { day: "numeric", month: "short", year: "numeric" })} · {a.renewalInDays} days · {a.renewalStage}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Wallet</dt>
              <dd className="font-medium tabular">{a.walletLabel}</dd>
            </div>
            {a.csm ? (
              <div>
                <dt className="text-muted-foreground">CSM</dt>
                <dd className="font-medium">{a.csm.name}</dd>
              </div>
            ) : null}
            {a.ae ? (
              <div>
                <dt className="text-muted-foreground">Sales rep</dt>
                <dd className="font-medium">{a.ae.name}</dd>
              </div>
            ) : null}
          </dl>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button size="lg" onClick={() => investigate("guided")} disabled={starting || running}>
              <Search className="size-4" /> {running ? "Investigating…" : active ? "Investigate again" : "Investigate"}
            </Button>
            {llm ? (
              <Button size="lg" variant="outline" onClick={() => investigate("gemini")} disabled={starting || running} title="Gemini picks each step of the investigation (via MCP)">
                <Bot className="size-4" /> Investigate with Gemini
              </Button>
            ) : null}
            {data.meetings.find((m) => m.status === "scheduled") ? (
              <Button size="lg" variant="ghost" asChild>
                <Link href={`/meetings/${data.meetings.find((m) => m.status === "scheduled")!.id}`}>
                  <CalendarClock className="size-4" /> Next call brief
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
        <Card className="self-start p-5">
          <HealthVsRisk crm={a.crmHealthScore} risk={r.risk} previous={a.detectiveRisk !== r.risk ? a.detectiveRisk : null} />
          <p className="mt-3 text-[12px] text-muted-foreground">Recomputed from the graph · {r.asOf}</p>
        </Card>
      </div>

      {active ? (
        <section className="mt-8" aria-label="Investigation">
          <InvestigationView id={active} onDone={() => mutate(`/api/accounts/${id}`)} onStatus={setInvStatus} />
        </section>
      ) : data.pastInvestigations.length ? (
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-4 text-[13.5px]">
          <History className="size-4 text-muted-foreground" aria-hidden />
          <span className="min-w-0 flex-1">
            Last investigation {formatDay(data.pastInvestigations[0].at)}: <b>{data.pastInvestigations[0].headline}</b>
          </span>
          {data.investigation ? (
            <Button size="sm" variant="outline" onClick={() => setInvId(data.investigation!.id)}>
              Open it
            </Button>
          ) : null}
        </Card>
      ) : null}

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[16px] font-semibold">
              Why {r.risk}% <span className="font-normal text-muted-foreground tabular">· {r.factors.length} factors</span>
            </h2>
            <button type="button" onClick={() => setShowQueries((v) => !v)} className="inline-flex items-center gap-1 text-[12.5px] text-muted-foreground hover:text-foreground" title="Show the graph query (Cypher)">
              <Code2 className="size-3.5" /> {showQueries ? "Hide" : "Show"} Cypher
            </button>
          </div>
          <FactorList factors={r.factors} base={6} />
          {showQueries ? (
            <div className="mt-3 space-y-2">
              {Object.entries(r.queries).map(([k, q]) => (
                <div key={k} className="rounded-xl bg-background p-2">
                  <p className="text-[11px] font-medium text-muted-foreground">{k}</p>
                  <pre className="mt-1 overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-snug">{q}</pre>
                </div>
              ))}
            </div>
          ) : null}
        </Card>

        <Card className="p-5">
          <CardTitle icon={Users}>People</CardTitle>
          <p className="mt-3 text-[12px] font-medium text-muted-foreground">At {a.name}</p>
          <ul className="mt-1 divide-y">
            {data.contacts.map((c) => (
              <li key={c.id} className="flex items-center gap-3 py-2.5">
                <Avatar name={c.name} size={30} />
                <div className="min-w-0 flex-1">
                  <p className={cn("font-medium leading-tight", !c.active && "text-muted-foreground line-through decoration-1")}>
                    {c.name}
                    {c.champion ? <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-foreground/70 no-underline">Main contact</span> : null}
                  </p>
                  <p className="text-[12.5px] text-muted-foreground">
                    {c.title}
                    {c.left ? ` · left ${formatDay(c.left)}${c.emailStatus === "bouncing" ? ", emails now bounce" : ""}` : ""}
                    {c.replaced ? ` · took over from ${c.replaced}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-[12px] font-medium text-muted-foreground">At Cheerio</p>
          <ul className="mt-1 divide-y">
            {data.owners.people.slice(0, 6).map((p) => (
              <li key={p.id} className="flex items-center gap-3 py-2.5">
                <Avatar name={p.name} size={30} ring={p.leaving ? "risk" : undefined} />
                <div className="min-w-0 flex-1">
                  <Link href={`/people/${p.id}`} className="font-medium leading-tight hover:underline">
                    {p.name}
                  </Link>
                  <p className="text-[12.5px] text-muted-foreground">
                    {p.relations.length ? p.relations.join(", ") : `knows the account (${(p.knows ?? 0).toFixed(2)})`} · {p.role}
                  </p>
                </div>
                {p.leaving ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2 py-0.5 text-[11.5px] font-medium text-warn">
                    <DoorOpen className="size-3" /> leaves {formatDay(p.lastDay)}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <CardTitle icon={Handshake}>Promises</CardTitle>
          {data.promises.length ? (
            <ul className="mt-3 space-y-2">
              {data.promises.map((p) => (
                <PromiseItem key={p.id} p={p} />
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[13.5px] text-muted-foreground">No promises are recorded for this account.</p>
          )}
        </Card>

        <Card className="p-5">
          <CardTitle icon={Bug}>Bugs behind their tickets</CardTitle>
          {data.issues.length ? (
            <ul className="mt-3 space-y-2">
              {data.issues.map((c) => (
                <li key={c.bugId} className="rounded-xl border p-3">
                  <p className="flex flex-wrap items-center gap-2">
                    <Dot tone={c.open ? "risk" : "covered"} />
                    <span className="font-mono text-[12px]">{c.bugId}</span>
                    <span className="font-medium">{c.bugTitle}</span>
                  </p>
                  <p className="mt-0.5 text-[12.5px] text-muted-foreground">
                    {c.jiraStatus ?? c.bugStatus} · {c.bugPriority} · {c.owner} · {c.tickets.length} tickets: {c.tickets.map((t) => `“${t.title}”`).join(", ")}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[13.5px] text-muted-foreground">No recent tickets trace to a bug.</p>
          )}
        </Card>

        <Card className="p-5">
          <CardTitle icon={Activity}>Usage</CardTitle>
          <p className="text-[12px] text-muted-foreground">{data.usage.window}</p>
          {data.usage.weeklyActiveUsers ? (
            <UsageLine name="Active users" m={data.usage.weeklyActiveUsers} />
          ) : null}
          {data.usage.featureDeclines.slice(0, 4).map((m) => (
            <UsageLine key={m.key} name={m.metric} m={m} />
          ))}
        </Card>

        <Card className="p-5">
          <CardTitle icon={CalendarClock}>Meetings and timeline</CardTitle>
          <ul className="mt-3 space-y-1.5">
            {data.meetings.map((m) => (
              <li key={m.id}>
                <Link href={`/meetings/${m.id}`} className="flex items-center gap-2 rounded-xl px-2 py-1.5 text-[13.5px] hover:bg-background">
                  <CalendarClock className="size-3.5 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{m.title}</span>
                  <span className="text-[12px] text-muted-foreground tabular">
                    {m.status === "scheduled" ? "upcoming" : formatDay(m.date)}
                    {m.promises ? ` · ${m.promises} promises` : ""}
                  </span>
                  <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
          <ol className="mt-4 space-y-2 border-l pl-4">
            {data.timeline.slice(-10).map((e, i) => (
              <li key={i} className="relative text-[13px]">
                <span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-foreground/40" aria-hidden />
                <span className="text-[11.5px] text-muted-foreground tabular">{e.date}</span> · {e.label}
              </li>
            ))}
          </ol>
        </Card>
      </div>

      {data.actions.length || data.memory.length ? (
        <Card className="mt-6 p-5">
          <CardTitle icon={History}>Past investigations and actions</CardTitle>
          <ul className="mt-3 divide-y text-[13.5px]">
            {data.memory.map((m) => (
              <li key={m.id} className="py-2.5">
                <span className="text-muted-foreground">
                  {m.at} · {m.kind}
                  {m.by ? ` · ${m.by}` : ""}
                </span>
                <p>{m.verdict}</p>
                {m.outcome ? <p className="text-[12.5px] text-muted-foreground">{m.outcome}</p> : null}
              </li>
            ))}
            {data.actions.map((x) => (
              <li key={x.id} className="flex items-start gap-3 py-2.5">
                <span className="min-w-0 flex-1">
                  {x.title} <span className="text-muted-foreground">· approved by {x.approvedBy}</span>
                  {x.message ? <span className="block text-[12.5px] text-muted-foreground">{x.message}</span> : null}
                </span>
                <ModeBadge mode={x.status === "succeeded" ? "live" : x.status === "drafted" ? "draft" : "simulated"} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function PromiseItem({ p }: { p: PromiseRow }) {
  return (
    <li className={cn("rounded-xl border p-3", p.atRisk && "border-warn/40")}>
      <p className={cn("font-medium leading-snug", p.status === "superseded" && "text-muted-foreground line-through decoration-1")}>{p.text}</p>
      <p className="mt-0.5 text-[12.5px] text-muted-foreground">
        {p.madeBy ?? "—"} · {p.meeting ?? "meeting"} · due {p.due} ·{" "}
        <span className={cn("font-medium", p.atRisk ? "text-warn" : p.status === "kept" ? "text-covered" : "")}>
          {p.atRisk ? `at risk: ${p.why?.split("(").pop()?.replace(")", "")}` : p.status === "superseded" ? "replaced" : p.status}
        </span>
      </p>
      {p.quote ? <p className="mt-1 text-[12.5px] italic text-muted-foreground">“{p.quote}”</p> : null}
    </li>
  );
}

function UsageLine({ name, m }: { name: string; m: { baseline: number; current: number; declinePct: number; series?: { week: string; value: number }[]; missingWeeks: number[] } }) {
  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="font-medium">{name}</span>
        <span className={cn("tabular", m.declinePct >= 20 ? "text-risk" : m.declinePct <= -3 ? "text-covered" : "text-muted-foreground")}>
          {m.declinePct > 0 ? `−${m.declinePct}%` : `+${-m.declinePct}%`} · {m.baseline} → {m.current} / week
        </span>
      </div>
      {m.series ? <Sparkbars series={m.series} className="mt-1.5 h-10" /> : null}
      {m.missingWeeks.length ? <p className="mt-1 text-[11px] text-muted-foreground">No data for week {m.missingWeeks.join(", ")}.</p> : null}
    </div>
  );
}

function AccountSkeleton() {
  return (
    <div className="mx-auto max-w-[1240px] px-4 py-10 md:px-8">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="mt-3 h-10 w-80" />
      <Skeleton className="mt-8 h-[300px]" />
    </div>
  );
}
