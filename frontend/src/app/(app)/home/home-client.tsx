"use client";

import Link from "next/link";
import useSWR from "swr";
import { ArrowRight, ChevronRight } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { greeting } from "@/lib/relay";
import { CsmHome, HeadOfCsHome } from "@/components/home/revenue-home";
import { CoverageBar } from "@/components/relay/coverage-bar";
import { Avatar, Card, CardTitle, PageHeader, Skeleton, TYPE_META, TypeIcon, formatDay } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { JourneyCard } from "@/components/workspace/journey";
import type { Home, ItemType } from "@/lib/types";

const ORDER: ItemType[] = ["System", "Account", "Decision", "Workaround"];


/** Home by role: the Head of CS and CSMs start from accounts, everyone else from knowledge risk. */
export function HomeClient() {
  const { personaInfo, session } = useApp();
  if (!session || !personaInfo) return <HomeSkeleton />;
  if (session.modules.accountHealth && personaInfo.persona === "head_cs") return <HeadOfCsHome />;
  if (session.modules.accountHealth && personaInfo.persona === "csm") return <CsmHome />;
  return <KnowledgeHome />;
}

function KnowledgeHome() {
  const { user, workspace, session } = useApp();
  const company = session?.demo.company ?? "the company";
  const leaver = session?.personas.find((p) => p.persona === "leaver");
  const { data } = useSWR<Home>("/api/home/knowledge-risk", { refreshInterval: 8000 });
  if (!data) return <HomeSkeleton />;
  const max = Math.max(...data.people.map((p) => p.unique), 1);
  const active = data.activeHandovers[0];
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-10 md:px-8">
      <PageHeader
        eyebrow={workspace?.name ?? company}
        title={`${greeting(session?.demo.now)}, ${user?.name.split(" ")[0]}.`}
        subtitle={`Where knowledge is at risk across ${company}.`}
        actions={
          active ? (
            <Button asChild size="lg">
              <Link href={`/handovers/${active.id}`}>
                Resume {active.leaver.name.split(" ")[0]}&apos;s handover <ArrowRight />
              </Link>
            </Button>
          ) : (
            <Button asChild size="lg">
              <Link href={`/people/${data.people[0]?.id ?? ""}`}>
                Start a handover <ArrowRight />
              </Link>
            </Button>
          )
        }
      />

      <div className="mt-8">
        <JourneyCard />
      </div>

      <section className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]" aria-label="Company overview">
        <Card className="p-5">
          <p className="text-[13px] font-medium text-muted-foreground">Single points of failure</p>
          <div className="mt-2 flex items-baseline gap-3">
            <span className="text-[44px] font-semibold leading-none tracking-[-0.4px] tabular" aria-live="polite">
              {data.singlePointsOfFailure}
            </span>
            <span
              className="text-[15px] text-muted-foreground"
              title="Only one person has a strong link to each item in Slack, docs, tickets, meetings or code."
            >
              things only one person knows
            </span>
          </div>
          <ul className="mt-5 grid grid-cols-2 gap-2">
            {ORDER.map((t) => (
              <li key={t} className="flex items-center gap-2 rounded-xl border px-3 py-2.5">
                <TypeIcon type={t} />
                <span className="text-[14px]">{TYPE_META[t].plural}</span>
                <span className="ml-auto font-semibold tabular">{data.byType[t] ?? 0}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <CardTitle
            action={
              <Link href="/handovers" className="text-[13px] text-muted-foreground hover:text-primary">
                All handovers
              </Link>
            }
          >
            Active handovers
          </CardTitle>
          {data.activeHandovers.length === 0 ? (
            data.closedHandovers.length ? (
              <div className="mt-4 rounded-xl border border-dashed p-6 text-center">
                <p className="font-medium">No active handovers</p>
                <p className="mt-1 text-[13px] text-muted-foreground">{data.closedHandovers.length} closed. Every item verified or dismissed.</p>
                <Button asChild variant="outline" size="sm" className="mt-4">
                  <Link href={`/handovers/${data.closedHandovers[0].id}`}>See {data.closedHandovers[0].leaver.name.split(" ")[0]}&apos;s handover</Link>
                </Button>
              </div>
            ) : (
              <div className="mt-4 rounded-xl border border-dashed p-6 text-center">
                <p className="font-medium">No handovers yet</p>
                <p className="mt-1 text-[13px] text-muted-foreground">
                  {leaver ? `${leaver.name.split(" ")[0]} leaves on Friday.` : "Start one from a person's profile."}
                </p>
                <Button asChild variant="outline" size="sm" className="mt-4">
                  <Link href={`/people/${leaver?.id ?? "p-rahul"}`}>Open {leaver?.name.split(" ")[0] ?? "the leaver"}&apos;s profile</Link>
                </Button>
              </div>
            )
          ) : (
            <ul className="mt-4 space-y-2">
              {data.activeHandovers.map((h) => (
                <li key={h.id}>
                  <Link href={`/handovers/${h.id}`} className="block rounded-xl border p-4 transition-colors hover:bg-background">
                    <div className="flex items-center gap-3">
                      <Avatar name={h.leaver.name} size={36} />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{h.leaver.name}</p>
                        <p className="text-[13px] text-muted-foreground">
                          Last day {formatDay(h.lastDay, { weekday: "short" })}
                          {h.joiner ? ` · ${h.joiner.name.split(" ")[0]} takes over` : ""}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-[22px] font-semibold leading-none tabular">{h.coverage.atRisk}</p>
                        <p className="text-[11px] text-muted-foreground">at risk</p>
                      </div>
                      <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                    </div>
                    <CoverageBar coverage={h.coverage} className="mt-4" legend />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <section className="mt-6" aria-label="People ranked by what only they know">
        <Card className="overflow-hidden">
          <CardTitle
            className="px-5 pb-2 pt-5"
            action={
              <Link href="/people" className="text-[13px] text-muted-foreground hover:text-primary">
                Everyone
              </Link>
            }
          >
            Who holds knowledge alone
          </CardTitle>
          <div className="px-2 pb-2">
            {data.people.map((p) => (
              <Link key={p.id} href={`/people/${p.id}`} className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-background">
                <Avatar name={p.name} size={32} />
                <div className="min-w-0 flex-1">
                  <p className="font-medium leading-tight">{p.name}</p>
                  <p className="text-[13px] text-muted-foreground">
                    {p.role} · {p.team}
                  </p>
                </div>
                <div className="hidden items-center gap-3 text-xs text-muted-foreground sm:flex">
                  {ORDER.filter((t) => p.byType[t]).map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 tabular" title={TYPE_META[t].plural}>
                      <TypeIcon type={t} className="size-3.5" />
                      {p.byType[t]}
                    </span>
                  ))}
                </div>
                <div className="hidden w-28 md:block" aria-hidden>
                  <div className="h-1.5 rounded-full bg-secondary">
                    <div className="h-1.5 rounded-full bg-primary/70" style={{ width: `${(p.unique / max) * 100}%` }} />
                  </div>
                </div>
                <span
                  className="w-[84px] text-right text-[14px] font-medium tabular"
                  title="No other active teammate has a strong link (above 0.4) to these."
                >
                  {p.unique} unique
                </span>
              </Link>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}

function HomeSkeleton() {
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-10 md:px-8">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="mt-3 h-10 w-80" />
      <Skeleton className="mt-8 h-14" />
      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
