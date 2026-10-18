"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { CalendarClock, ChevronRight, FileText, Radio } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { MeetingRow } from "@/components/home/revenue-home";
import { Card, CardTitle, EmptyState, PageHeader, Skeleton, formatDay } from "@/components/relay/primitives";
import type { UpcomingMeeting } from "@/lib/relay";
import { cn } from "@/lib/utils";

interface Meetings {
  upcoming: UpcomingMeeting[];
  recent: { id: string; title: string; start: string; accountId: string; account: string; promises: number; summarySource: string | null }[];
}

export function MeetingsClient() {
  const { persona, session } = useApp();
  const [mine, setMine] = useState(false);
  const { data } = useSWR<Meetings>(`/api/meetings${mine ? "?mine=true" : ""}`, { refreshInterval: 15_000 });
  if (!session?.modules.salesAssist) {
    return (
      <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8">
        <EmptyState title="No customer calendar connected" body="Connect a CRM, a calendar and a meeting bot to use Sales Assist." />
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-[1100px] px-4 py-10 md:px-8">
      <PageHeader eyebrow="Sales Assist" title="Meetings" subtitle="A brief before each call, live help during it." />
      <div className="mt-6 flex gap-1" role="tablist" aria-label="Show meetings">
        {[
          { v: false, l: "Everyone's" },
          { v: true, l: "Mine" },
        ].map((t) => (
          <button
            key={t.l}
            role="tab"
            aria-selected={mine === t.v}
            onClick={() => setMine(t.v)}
            className={cn("rounded-full px-3 py-1 text-[13px] font-medium", mine === t.v ? "bg-foreground text-background" : "text-muted-foreground hover:bg-secondary")}
            disabled={t.v && !persona}
          >
            {t.l}
          </button>
        ))}
      </div>
      <section className="mt-4">
        <Card className="p-5">
          <CardTitle icon={CalendarClock}>This week</CardTitle>
          {!data ? (
            <Skeleton className="mt-4 h-40" />
          ) : data.upcoming.length ? (
            <ul className="mt-4 space-y-2">
              {data.upcoming.map((m) => (
                <li key={m.id}>
                  <MeetingRow m={m} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-muted-foreground">No meetings this week.</p>
          )}
        </Card>
      </section>
      <section className="mt-6">
        <Card className="p-5">
          <CardTitle icon={FileText}>Past customer meetings</CardTitle>
          <ul className="mt-3 divide-y">
            {(data?.recent ?? []).map((m) => (
              <li key={m.id}>
                <Link href={`/meetings/${m.id}`} className="-mx-2 flex items-center gap-3 rounded-xl px-2 py-2.5 text-[14px] transition-colors hover:bg-background">
                  {m.summarySource === "Relay live call" ? <Radio className="size-3.5 text-primary" aria-label="Recorded by Relay" /> : <span className="size-3.5" />}
                  <span className="min-w-0 flex-1 truncate">{m.title}</span>
                  <span className="text-right text-[12.5px] text-muted-foreground tabular">
                    {formatDay(m.start)}
                    {m.promises ? ` · ${m.promises} promise${m.promises > 1 ? "s" : ""}` : ""}
                  </span>
                  <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </section>
    </div>
  );
}
