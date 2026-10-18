"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { useCompany } from "@/components/app-provider";
import { Avatar, Card, PageHeader, Skeleton, formatDay } from "@/components/relay/primitives";
import type { PersonRow } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PeopleClient() {
  const company = useCompany();
  const { data } = useSWR<PersonRow[]>("/api/people");
  const [team, setTeam] = useState<string>("All");
  const teams = useMemo(() => ["All", ...Array.from(new Set((data ?? []).map((p) => p.team)))], [data]);
  const rows = (data ?? []).filter((p) => team === "All" || p.team === team);
  return (
    <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8">
      <PageHeader eyebrow={company} title="People" subtitle={data ? `${data.length} people and what only they know.` : "Loading…"} />
      <div className="mt-8 flex flex-wrap gap-1" role="tablist" aria-label="Filter by team">
        {teams.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={team === t}
            onClick={() => setTeam(t)}
            className={cn(
              "rounded-full px-3 py-1 text-[13px] font-medium transition-colors",
              team === t ? "bg-foreground text-background" : "text-muted-foreground hover:bg-secondary",
            )}
          >
            {t}
          </button>
        ))}
      </div>
      {!data ? (
        <Skeleton className="mt-4 h-96" />
      ) : (
        <Card className="mt-4 divide-y">
          {rows.map((p) => (
            <Link key={p.id} href={`/people/${p.id}`} className="flex items-center gap-3 px-5 py-3 transition-colors first:rounded-t-2xl last:rounded-b-2xl hover:bg-background">
              <Avatar name={p.name} size={30} />
              <div className="min-w-0 flex-1">
                <p className="font-medium leading-tight">{p.name}</p>
                <p className="text-[13px] text-muted-foreground">
                  {p.role} · {p.team}
                </p>
              </div>
              {p.status === "joining" ? (
                <span className="rounded-full bg-brand-soft px-2 py-0.5 text-xs text-brand">Joins {formatDay(p.startDate)}</span>
              ) : null}
              {p.lastDay ? <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground">Last day {formatDay(p.lastDay)}</span> : null}
              <span className={cn("w-[84px] text-right text-sm tabular", p.unique ? "font-medium" : "text-muted-foreground")}>
                {p.unique ? `${p.unique} unique` : "0 unique"}
              </span>
            </Link>
          ))}
        </Card>
      )}
    </div>
  );
}
