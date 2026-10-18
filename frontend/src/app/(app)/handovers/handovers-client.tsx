"use client";

import Link from "next/link";
import useSWR from "swr";

import { CoverageBar } from "@/components/relay/coverage-bar";
import { Avatar, Card, EmptyState, PageHeader, Skeleton, formatDay } from "@/components/relay/primitives";
import type { HandoverSummary } from "@/lib/types";

export function HandoversClient() {
  const { data } = useSWR<HandoverSummary[]>("/api/handovers");
  return (
    <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8">
      <PageHeader eyebrow="Knowledge" title="Handovers" subtitle="Pass what a leaver knows to the people who stay." />
      <div className="mt-8">
        {!data ? (
          <Skeleton className="h-40" />
        ) : data.length === 0 ? (
          <EmptyState title="No handovers yet" body="Start one from a person's profile." action={<Link className="text-sm text-primary hover:underline" href="/people">Browse people →</Link>} />
        ) : (
          <Card className="divide-y">
            {data.map((h) => (
              <Link key={h.id} href={`/handovers/${h.id}`} className="block px-5 py-4 transition-colors first:rounded-t-2xl last:rounded-b-2xl hover:bg-background">
                <div className="flex items-center gap-3">
                  <Avatar name={h.leaver.name} size={32} />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium leading-tight">{h.leaver.name}</p>
                    <p className="text-[13px] text-muted-foreground">Last day {formatDay(h.lastDay, { weekday: "short" })}</p>
                  </div>
                  <span className="text-right text-[13px] text-muted-foreground tabular">
                    {h.status === "closed" ? (
                      "Closed"
                    ) : (
                      <>
                        <b className="text-[15px] font-semibold text-foreground">{h.coverage.atRisk}</b> of {h.coverage.total} at risk
                      </>
                    )}
                  </span>
                </div>
                <CoverageBar coverage={h.coverage} className="mt-3" />
              </Link>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}
