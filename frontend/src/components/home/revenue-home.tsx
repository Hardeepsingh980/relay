"use client";

import Link from "next/link";
import useSWR from "swr";
import { ArrowRight, Bug, CalendarClock, ChevronRight, DoorOpen } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { CrmScore, ModeBadge, RiskNumber, SilentBadge } from "@/components/health/bits";
import { Avatar, Card, CardTitle, PageHeader, Skeleton, formatDay } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { JourneyCard } from "@/components/workspace/journey";
import { dayIST, greeting, inr, timeIST, type ActionLogRow, type CostlyBug, type RadarRow, type UpcomingMeeting } from "@/lib/relay";
import { cn } from "@/lib/utils";

interface Leaving {
  id: string;
  name: string;
  role: string;
  lastDay: string;
  handoverId: string | null;
  handoverStatus: string | null;
  knows: number;
  accounts: { id: string; name: string; why: string[] }[];
}

export interface Overview {
  asOf: string;
  leaving: Leaving[];
  silent: { count: number; arr: number; arrLabel: string };
  silentAccounts: RadarRow[];
  topRisks: RadarRow[];
  mine: RadarRow[];
  renewing: RadarRow[];
  meetings: UpcomingMeeting[];
  myMeetings: UpcomingMeeting[];
  costliestBug: CostlyBug | null;
  actions: ActionLogRow[];
  portfolio: { accounts: number; arr: number; arrLabel: string; atRisk: number };
}


export function AccountRow({ a, compact }: { a: RadarRow; compact?: boolean }) {
  return (
    <Link href={`/accounts/${a.id}`} className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-background">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-secondary text-[13px] font-semibold">{a.name[0]}</span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 font-medium leading-tight">
          {a.name}
          {a.silent && !compact ? <SilentBadge /> : null}
        </p>
        <p className="truncate text-[13px] text-muted-foreground">{a.hint}</p>
      </div>
      <div className="hidden w-[92px] text-right text-[12.5px] text-muted-foreground sm:block">
        <p className="font-medium text-foreground tabular">{a.arrLabel}</p>
        <p className="tabular">renews in {a.renewalInDays}d</p>
      </div>
      <CrmScore crm={a.crm} className="hidden md:inline-flex" />
      <RiskNumber risk={a.risk} previous={a.previousRisk} className="w-[64px] justify-end" />
      <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
    </Link>
  );
}

export function MeetingRow({ m }: { m: UpcomingMeeting }) {
  const today = m.startsIn < 24 * 60 && m.startsIn > -60;
  return (
    <Link href={`/meetings/${m.id}`} className="flex items-center gap-3 rounded-xl border p-3 transition-colors hover:bg-background">
      <div className={cn("flex w-14 shrink-0 flex-col items-center rounded-xl py-1.5", today ? "bg-brand-soft text-primary" : "bg-secondary")}>
        <span className="text-[10px] font-medium uppercase">{dayIST(m.start, { weekday: "short" })}</span>
        <span className="text-[15px] font-semibold tabular">{timeIST(m.start)}</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium leading-tight">{m.title}</p>
        <p className="truncate text-[12.5px] text-muted-foreground">
          {m.attendees.filter((x) => !x.internal).map((x) => x.name).join(", ")}
          {m.recording ? " · recording" : ""}
        </p>
      </div>
      {m.silent ? <SilentBadge className="hidden sm:inline-flex" /> : null}
      <RiskNumber risk={m.risk} size="sm" />
      <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
    </Link>
  );
}

function LeavingCard({ people }: { people: Leaving[] }) {
  if (!people.length) return null;
  return (
    <Card className="p-5">
      <CardTitle icon={DoorOpen}>People leaving</CardTitle>
      <ul className="mt-4 space-y-2">
        {people.map((p) => (
          <li key={p.id} className="rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <Avatar name={p.name} size={36} ring="risk" />
              <div className="min-w-0 flex-1">
                <p className="font-medium leading-tight">{p.name}</p>
                <p className="text-[13px] text-muted-foreground">
                  {p.role} · last day {formatDay(p.lastDay, { weekday: "long", day: "numeric", month: "short" })}
                </p>
              </div>
              <Button asChild size="sm" variant={p.handoverId ? "outline" : "default"}>
                <Link href={p.handoverId ? `/handovers/${p.handoverId}` : `/people/${p.id}`}>
                  {p.handoverId ? "Open handover" : "Start handover"}
                </Link>
              </Button>
            </div>
            {p.accounts.length ? (
              <p className="mt-3 text-[13px] text-muted-foreground">
                Customers who depend on {p.name.split(" ")[0]}:{" "}
                {p.accounts.map((a, i) => (
                  <span key={a.id}>
                    {i ? ", " : ""}
                    <Link href={`/accounts/${a.id}`} className="font-medium text-foreground underline-offset-2 hover:underline" title={a.why.join(", ")}>
                      {a.name}
                    </Link>
                  </span>
                ))}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CostliestBug({ bug }: { bug: CostlyBug }) {
  return (
    <Card className="p-5">
      <CardTitle icon={Bug}>Costliest open bug</CardTitle>
      <p className="mt-3 text-[15px]">
        <span className="font-mono text-[13px]">{bug.bugId}</span> · {bug.title}
      </p>
      <div className="mt-4 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <span>
          <span className="text-[28px] font-semibold tabular">{inr(bug.arr)}</span>
          <span className="ml-1.5 text-[13px] text-muted-foreground">ARR across {bug.accounts} accounts</span>
        </span>
        <span className="text-[13px] text-muted-foreground">
          {bug.tickets} tickets · {bug.jiraStatus ?? bug.status} at <b className={cn(bug.underPrioritised && "text-risk")}>{bug.priority}</b> · owner {bug.owner}
        </span>
      </div>
      {bug.underPrioritised ? <p className="mt-3 text-[13px] font-medium text-risk">Priority is too low for the revenue at risk.</p> : null}
    </Card>
  );
}

function ActionLog({ rows }: { rows: ActionLogRow[] }) {
  if (!rows.length) return null;
  return (
    <Card className="p-5">
      <CardTitle>Recent actions</CardTitle>
      <ul className="mt-3 divide-y">
        {rows.map((r) => (
          <li key={r.id} className="flex items-start gap-3 py-2.5 text-[13.5px]">
            <span className="min-w-0 flex-1">
              <span className="block font-medium leading-snug">{r.title}</span>
              <span className="block text-[12px] text-muted-foreground">
                {r.account ? `${r.account} · ` : ""}approved by {r.approvedBy}
              </span>
            </span>
            <ModeBadge mode={r.status === "succeeded" ? "live" : r.status === "drafted" ? "draft" : "simulated"} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Header({ title, subtitle, cta }: { title: string; subtitle: string; cta?: React.ReactNode }) {
  const { workspace, session } = useApp();
  return <PageHeader eyebrow={workspace?.name ?? session?.demo.company} title={title} subtitle={subtitle} actions={cta} />;
}

function useOverview() {
  return useSWR<Overview>("/api/home/overview", { refreshInterval: 10_000 });
}

export function HeadOfCsHome() {
  const { user, session } = useApp();
  const { data } = useOverview();
  if (!data?.portfolio) return <HomeSkeleton />;
  const today = data.meetings.filter((m) => m.startsIn < 24 * 60);
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-10 md:px-8">
      <Header
        title={`${greeting(session?.demo.now)}, ${user?.name.split(" ")[0]}.`}
        subtitle={`${data.silent.count} accounts look healthy in HubSpot but are at risk.`}
        cta={
          <Button asChild size="lg">
            <Link href="/accounts">
              Open Risk Radar <ArrowRight />
            </Link>
          </Button>
        }
      />
      <div className="mt-8">
        <JourneyCard />
      </div>
      <section className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Card className="p-5">
          <CardTitle
            action={
              <Link href="/accounts?silent=1" className="text-[13px] text-muted-foreground hover:text-primary">
                See all
              </Link>
            }
          >
            Silent risk
          </CardTitle>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-[44px] font-semibold leading-none tracking-[-0.4px] text-risk tabular">{data.silent.count}</span>
            <span className="text-[15px] text-muted-foreground">accounts · {data.silent.arrLabel} ARR</span>
          </div>
          <p className="mt-1 text-[13px] text-muted-foreground" title={`HubSpot health 70+ but Relay risk 60%+. ${data.portfolio.atRisk} of ${data.portfolio.accounts} accounts (${data.portfolio.arrLabel} ARR) are at high risk.`}>
            Healthy in HubSpot, at risk in Relay.
          </p>
          <div className="mt-3 -mx-3">
            {data.silentAccounts.map((a) => (
              <AccountRow key={a.id} a={a} compact />
            ))}
          </div>
        </Card>
        <div className="space-y-6">
          <LeavingCard people={data.leaving} />
          <Card className="p-5">
            <CardTitle
              icon={CalendarClock}
              action={
                <Link href="/meetings" className="text-[13px] text-muted-foreground hover:text-primary">
                  All meetings
                </Link>
              }
            >
              Customer calls
            </CardTitle>
            <ul className="mt-4 space-y-2">
              {(today.length ? today : data.meetings).slice(0, 3).map((m) => (
                <li key={m.id}>
                  <MeetingRow m={m} />
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </section>
      <section className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Card className="p-2">
          <CardTitle
            className="px-3 pb-1 pt-3"
            action={
              <Link href="/accounts" className="text-[13px] text-muted-foreground hover:text-primary">
                Risk Radar
              </Link>
            }
          >
            Renewing in 45 days
          </CardTitle>
          {data.renewing.map((a) => (
            <AccountRow key={a.id} a={a} />
          ))}
        </Card>
        <div className="space-y-6">
          {data.costliestBug ? <CostliestBug bug={data.costliestBug} /> : null}
          <ActionLog rows={data.actions} />
        </div>
      </section>
    </div>
  );
}

export function CsmHome() {
  const { user, session } = useApp();
  const { data } = useOverview();
  if (!data?.portfolio) return <HomeSkeleton />;
  const next = data.myMeetings[0];
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-10 md:px-8">
      <Header
        title={`${greeting(session?.demo.now)}, ${user?.name.split(" ")[0]}.`}
        subtitle={next ? `Your brief for ${next.account} at ${timeIST(next.start)} is ready.` : "No customer calls on your calendar."}
        cta={
          next ? (
            <Button asChild size="lg">
              <Link href={`/meetings/${next.id}`}>
                Open the brief <ArrowRight />
              </Link>
            </Button>
          ) : null
        }
      />
      <section className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="p-5">
          <CardTitle icon={CalendarClock}>Your calls this week</CardTitle>
          <ul className="mt-4 space-y-2">
            {data.myMeetings.map((m) => (
              <li key={m.id}>
                <MeetingRow m={m} />
              </li>
            ))}
          </ul>
        </Card>
        <LeavingCard people={data.leaving} />
      </section>
      <section className="mt-6">
        <Card className="p-2">
          <CardTitle
            className="px-3 pb-1 pt-3"
            action={
              <Link href="/accounts?mine=1" className="text-[13px] text-muted-foreground hover:text-primary">
                All your accounts
              </Link>
            }
          >
            Your accounts, riskiest first
          </CardTitle>
          {data.mine.map((a) => (
            <AccountRow key={a.id} a={a} />
          ))}
        </Card>
      </section>
    </div>
  );
}

export function HomeSkeleton() {
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
