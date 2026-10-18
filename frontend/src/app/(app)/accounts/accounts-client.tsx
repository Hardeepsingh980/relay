"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { toast } from "sonner";
import { ArrowDownUp, Bug, ChevronRight, RefreshCw, Search } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { CrmScore, RiskNumber, SilentBadge } from "@/components/health/bits";
import { Card, CardTitle, EmptyState, PageHeader, Skeleton } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { inr, type CostlyBug, type Radar, type RadarRow } from "@/lib/relay";
import { cn } from "@/lib/utils";

type Filter = "all" | "silent" | "renewing" | "mine";
type Sort = "risk" | "gap" | "arr" | "renewal";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "silent", label: "Silent risk" },
  { id: "renewing", label: "Renews within 45 days" },
  { id: "mine", label: "My accounts" },
];

/** The gap between how healthy the CRM thinks an account is and how risky the graph says it is. */
function gap(a: RadarRow) {
  return a.risk - (100 - a.crm);
}

export function AccountsClient() {
  const params = useSearchParams();
  const { persona } = useApp();
  const { mutate } = useSWRConfig();
  const { data } = useSWR<Radar>("/api/accounts", { refreshInterval: 15_000 });
  const { data: bugs } = useSWR<{ bugs: CostlyBug[] }>("/api/health/costliest-bugs");
  const [filter, setFilter] = useState<Filter>(params.get("mine") ? "mine" : params.get("silent") ? "silent" : "all");
  const [sort, setSort] = useState<Sort>("risk");
  const [q, setQ] = useState("");
  const [scanning, setScanning] = useState(false);
  useEffect(() => {
    api.post("/api/journey/radar").catch(() => null);
  }, []);

  const rows = useMemo(() => {
    let r = data?.accounts ?? [];
    if (filter === "silent") r = r.filter((a) => a.silent);
    if (filter === "renewing") r = r.filter((a) => a.renewalInDays >= 0 && a.renewalInDays <= 45);
    if (filter === "mine") r = r.filter((a) => a.csmId === persona);
    if (q.trim()) r = r.filter((a) => `${a.name} ${a.industry} ${a.csm ?? ""}`.toLowerCase().includes(q.trim().toLowerCase()));
    const by: Record<Sort, (a: RadarRow) => number> = {
      risk: (a) => -a.risk,
      gap: (a) => -gap(a),
      arr: (a) => -a.arr,
      renewal: (a) => a.renewalInDays,
    };
    return [...r].sort((a, b) => by[sort](a) - by[sort](b));
  }, [data, filter, sort, q, persona]);

  if (!data) return <RadarSkeleton />;
  if (!data.accounts.length)
    return (
      <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8">
        <EmptyState title="No customer data connected" body="Connect a CRM to see account risk here." />
      </div>
    );

  const rescan = async () => {
    setScanning(true);
    try {
      const r = await api.post<{ accounts: number; silent: number; ms: number }>("/api/health/scan");
      await mutate("/api/accounts");
      toast.success(`Relay rescanned ${r.accounts} accounts in ${r.ms} ms`, { description: `${r.silent} look healthy in HubSpot but are at risk` });
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-10 md:px-8">
      <PageHeader
        eyebrow={`Account Health · as of ${data.asOf}`}
        title="Risk Radar"
        subtitle={`${data.silent.count} accounts (${data.silent.arrLabel} ARR) look healthy in HubSpot but are at risk.`}
        actions={
          <Button variant="outline" onClick={rescan} disabled={scanning}>
            <RefreshCw className={cn("size-4", scanning && "animate-spin")} /> {scanning ? "Scanning…" : "Rescan all accounts"}
          </Button>
        }
      />

      <div className="mt-8 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <div role="tablist" aria-label="Filter accounts" className="flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  role="tab"
                  aria-selected={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    "rounded-full px-3 py-1 text-[13px] font-medium",
                    filter === f.id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-secondary",
                  )}
                >
                  {f.label}
                  {f.id === "silent" ? <span className="ml-1 tabular opacity-70">{data.silent.count}</span> : null}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search accounts" className="h-8 w-48 pl-8 text-[13px]" aria-label="Search accounts" />
              </div>
              <label className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
                <ArrowDownUp className="size-3.5" aria-hidden />
                <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="rounded-md bg-transparent py-1 text-foreground" aria-label="Sort by">
                  <option value="risk">Relay risk</option>
                  <option value="gap">HubSpot vs Relay gap</option>
                  <option value="arr">ARR</option>
                  <option value="renewal">Renewal date</option>
                </select>
              </label>
            </div>
          </div>
          <div className="hidden grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_88px_92px_80px_20px] gap-3 border-b bg-background/60 px-5 py-2 text-[12px] font-medium text-muted-foreground md:grid">
            <span>Account</span>
            <span>Owner · renewal</span>
            <span className="text-right">ARR</span>
            <span className="text-right">HubSpot</span>
            <span className="text-right" title="Risk of leaving, built from graph factors. Open an account to see each one.">
              Relay risk
            </span>
            <span />
          </div>
          <ul className="divide-y">
            {rows.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/accounts/${a.id}`}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-5 py-3 transition-colors hover:bg-background md:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_88px_92px_80px_20px]"
                >
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2 font-medium leading-tight">
                      {a.name}
                      {a.silent ? <SilentBadge /> : null}
                    </span>
                    <span className="block truncate text-[12.5px] text-muted-foreground">{a.hint}</span>
                  </span>
                  <span className="hidden min-w-0 text-[12.5px] text-muted-foreground md:block">
                    <span className="block truncate text-foreground/80">{a.csm ?? "—"}</span>
                    <span className="tabular">
                      {a.renewalInDays >= 0 ? `renews in ${a.renewalInDays}d` : `${-a.renewalInDays}d past renewal`} · {a.stage}
                    </span>
                  </span>
                  <span className="hidden text-right text-[13.5px] font-medium tabular md:block">{a.arrLabel}</span>
                  <span className="hidden justify-end md:flex">
                    <CrmScore crm={a.crm} />
                  </span>
                  <span className="flex justify-end">
                    <RiskNumber risk={a.risk} previous={a.previousRisk} size="sm" />
                  </span>
                  <ChevronRight className="hidden size-4 text-muted-foreground md:block" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
          {!rows.length ? <p className="px-5 py-10 text-center text-muted-foreground">No accounts match.</p> : null}
          <p className="border-t px-5 py-3 text-[12px] text-muted-foreground tabular">
            {rows.length} of {data.accounts.length} accounts
          </p>
        </Card>

        <aside className="space-y-6">
          <Card className="p-4">
            <CardTitle icon={Bug}>Costliest open bugs</CardTitle>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">By ARR of affected accounts</p>
            <ol className="mt-3 divide-y">
              {(bugs?.bugs ?? []).slice(0, 6).map((b) => (
                <li key={b.bugId} className="py-2.5 first:pt-0 last:pb-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-[12px]">{b.bugId}</span>
                    <span className="text-[14px] font-semibold tabular">{inr(b.arr)}</span>
                  </div>
                  <p className="mt-0.5 text-[13px] leading-snug">{b.title}</p>
                  <p className="mt-1 text-[11.5px] text-muted-foreground">
                    {b.accounts} accounts · {b.tickets} tickets ·{" "}
                    <span className={cn(b.underPrioritised && "font-semibold text-risk")}>{b.priority}</span> · {b.owner}
                  </p>
                </li>
              ))}
            </ol>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function RadarSkeleton() {
  return (
    <div className="mx-auto max-w-[1240px] px-4 py-10 md:px-8">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="mt-3 h-10 w-72" />
      <Skeleton className="mt-8 h-[520px]" />
    </div>
  );
}
