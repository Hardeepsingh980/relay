"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CalendarCheck, CalendarPlus, Check, FileText, Search, SquareKanban, Users } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { ActionReview } from "@/components/relay/actions-panel";
import { KnowledgeGraph, RelationshipList } from "@/components/relay/knowledge-graph";
import { Avatar, Card, EmptyState, Mono, PageHeader, SectionTitle, Skeleton, SourcePill, StateBadge, formatDay } from "@/components/relay/primitives";
import { renderCode } from "@/components/relay/source-drawer";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Action, ChecklistItem, DayOne, KnowledgeCard } from "@/lib/types";
import { cn } from "@/lib/utils";

const JOINER = "p-aisha";

export function DayOneClient() {
  const { persona, openAsk, openSource } = useApp();
  const who = persona === "p-priya" || persona === "p-rahul" ? JOINER : persona;
  const { data, mutate } = useSWR<DayOne>(`/api/day-one/${who}`, { refreshInterval: 10_000 });
  const [booking, setBooking] = useState<Action | null>(null);
  const [bookingFor, setBookingFor] = useState<string | null>(null);
  const [booked, setBooked] = useState<Record<string, Action>>({});

  if (!data) {
    return (
      <div className="mx-auto max-w-[1100px] px-4 py-10 md:px-8">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="mt-6 h-28" />
        <Skeleton className="mt-6 h-96" />
      </div>
    );
  }
  const first = data.person.name.split(" ")[0];
  if (!data.handover || !data.leaver) {
    return (
      <div className="mx-auto max-w-[1100px] px-4 py-10 md:px-8">
        <PageHeader eyebrow="Day one" title={`Welcome, ${first}.`} />
        <div className="mt-8">
          <EmptyState title="Your area is not ready yet" body="This page fills in once your handover starts." />
        </div>
      </div>
    );
  }
  const leaverFirst = data.leaver.name.split(" ")[0];
  const viewingOwn = persona === data.person.id;

  const book = async (personId: string) => {
    if (!viewingOwn) {
      toast("Preview only", { description: `To book a meeting, choose ${first} under View as.` });
      return;
    }
    try {
      const a = await api.post<Action>("/api/actions/intro", { personId });
      setBookingFor(personId);
      setBooking(a);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "The invite failed. Try again.");
    }
  };

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-10 md:px-8">
      {!viewingOwn ? (
        <p className="mb-6 rounded-xl border bg-card px-3 py-2 text-xs text-muted-foreground">Preview of {first}&apos;s Day One. Switch to {first} under View as to act on it.</p>
      ) : null}
      <section>
        <PageHeader
          eyebrow={`Day one · ${data.team}`}
          title={`Welcome, ${first}.`}
          subtitle={`You take over from ${leaverFirst}. Last day ${formatDay(data.leaver.lastDay, { weekday: "long", day: "numeric", month: "short" })}.`}
        />
        <div aria-label="Your services" className="mt-8 grid grid-cols-1 gap-3 md:grid-cols-3">
          {data.services?.map((s) => (
            <div key={s.id} className="rounded-2xl border bg-card p-5">
              <div className="flex items-start justify-between gap-2">
                <Mono className="text-[13.5px] font-medium">{s.name}</Mono>
                <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">{s.criticality}</span>
              </div>
              <p className="mt-2 text-[14px] text-muted-foreground">{s.summary}</p>
              <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted-foreground">
                <span className="tabular">{s.knowledge ? `${s.knowledge} answers from ${leaverFirst}` : `No answers from ${leaverFirst} yet`}</span>
                {s.openTickets.length ? <span>{s.openTickets.length} open tickets</span> : null}
                {s.successor ? <span>Next owner {s.successor.name.split(" ")[0]}</span> : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="space-y-10">
          <section aria-label="Meet these 5">
            <SectionTitle>Meet these {data.meet?.length ?? 5}</SectionTitle>
            <Card className="divide-y">
              {data.meet?.map((p) => {
                const b = booked[p.id];
                return (
                  <div key={p.id} className="flex items-center gap-3 px-4 py-3">
                    <Avatar name={p.name} size={32} />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium leading-tight">
                        {p.name} <span className="font-normal text-muted-foreground">· {p.role}</span>
                      </p>
                      <p className="mt-0.5 text-sm text-muted-foreground">{p.reason}</p>
                    </div>
                    {b ? (
                      <button type="button" onClick={() => { setBookingFor(p.id); setBooking(b); }} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                        <CalendarCheck className="size-3.5" /> {b.status === "succeeded" ? "Booked" : b.status === "simulated" ? "Saved in Relay" : b.status === "failed" ? "Failed" : "Review"}
                      </button>
                    ) : (
                      <Button size="sm" variant={p.urgent ? "default" : "outline"} onClick={() => book(p.id)}>
                        <CalendarPlus /> Book 30 min
                      </Button>
                    )}
                  </div>
                );
              })}
            </Card>
          </section>

          <section aria-label={`From ${leaverFirst}`}>
            <SectionTitle count={data.fromLeaver?.length}>From {leaverFirst}</SectionTitle>
            {!data.fromLeaver?.length ? (
              <EmptyState title={`Nothing from ${leaverFirst} yet`} body={`${leaverFirst}'s handover answers will show up here.`} />
            ) : (
              <div className="space-y-2">
                {data.fromLeaver.map((c) => (
                  <KnowledgeCardView key={c.id} card={c} />
                ))}
              </div>
            )}
          </section>

          <section aria-label="Your first week">
            <SectionTitle>Your first week</SectionTitle>
            <Card className="divide-y">
              {data.checklist?.map((c) => (
                <ChecklistRow
                  key={c.id}
                  item={c}
                  disabled={!viewingOwn}
                  onToggle={async () => {
                    await api.post(`/api/checklist/${c.id}/toggle`);
                    mutate();
                  }}
                  onOpen={() =>
                    c.targetLabel && c.targetId
                      ? openSource({ kind: c.kind === "ticket" ? "jira" : "doc", id: c.targetId, nodeLabel: c.targetLabel, title: c.label.replace(/^Read “|”$/g, ""), label: c.targetId })
                      : null
                  }
                />
              ))}
            </Card>
            {data.familiarWith?.length ? (
              <p className="mt-2 text-xs text-muted-foreground" title="Counts as some knowledge. Expert knowledge comes from your own commits, reviews and answers.">
                Already familiar with {data.familiarWith.join(", ")}.
              </p>
            ) : null}
          </section>
        </div>

        <aside className="space-y-6">
          <Card className="p-4">
            <h2 className="text-[16px] font-semibold">Your area</h2>
            <p className="text-xs text-muted-foreground">What you take over and who knows it</p>
            <div className="mt-2 h-[300px]">
              {data.graph ? (
                <KnowledgeGraph graph={data.graph} centerId={data.person.id} variant="dayone" className="h-full" label={`The area ${first} takes over`} />
              ) : null}
            </div>
            {data.graph ? <RelationshipList items={data.graph.relationships} /> : null}
          </Card>

          <section aria-label="Decisions behind your systems">
            <h2 className="mb-2 text-[16px] font-semibold">Decisions behind your systems</h2>
            <ul className="space-y-2">
              {data.decisions?.map((d) => (
                <li key={d.id} className="rounded-xl border bg-card p-3">
                  <p className="text-sm font-medium leading-snug">{d.summary}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {d.decidedLabel}
                    {d.knowledge ? <span className="text-brand">{leaverFirst} explained why</span> : d.rationaleStatus === "conversation-only" ? <span>Reason not in any doc</span> : <span>Reason in docs</span>}
                    {d.state && d.state !== "dismissed" ? <StateBadge state={d.state} className="px-1.5 py-0 text-[10px]" /> : null}
                  </p>
                  <button type="button" onClick={() => openAsk(`Why did we decide to ${d.summary[0].toLowerCase()}${d.summary.slice(1)}?`)} className="mt-1 text-xs text-primary hover:underline">
                    Ask why
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <button
            type="button"
            onClick={() => openAsk()}
            className="flex w-full items-center gap-3 rounded-xl border bg-card p-4 text-left text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <Search className="size-4" />
            <span className="flex-1">Ask why something is the way it is</span>
            <kbd className="rounded border px-1 text-[10px]">⌘K</kbd>
          </button>
        </aside>
      </div>

      {booking ? (
        <ActionReview
          action={booking}
          open
          onOpenChange={(o) => !o && setBooking(null)}
          onDone={(a) => {
            setBooking(a);
            if (bookingFor) setBooked((b) => ({ ...b, [bookingFor]: a }));
          }}
        />
      ) : null}
    </div>
  );
}

function KnowledgeCardView({ card }: { card: KnowledgeCard }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {card.system ? <Mono className="text-foreground">{card.system}</Mono> : null}
        <span>· {card.itemType === "System" || card.itemType === "Account" ? card.itemType.toLowerCase() : card.itemTitle}</span>
      </div>
      <p className="mt-2 text-sm font-medium leading-snug">{card.question}</p>
      <p className={cn("mt-1 leading-relaxed text-foreground/90", !open && "line-clamp-3")}>{renderCode(card.answer)}</p>
      {card.answer.length > 220 ? (
        <button type="button" onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-muted-foreground hover:text-foreground">
          {open ? "Show less" : "Read all"}
        </button>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Avatar name={card.author} size={18} />
        <span className="text-xs text-muted-foreground">
          {card.author} · {card.capturedLabel}
        </span>
        {card.verified ? (
          <span className="inline-flex items-center gap-1 text-xs text-covered">
            <Check className="size-3" /> Verified by {card.verifiedBy}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Not yet verified</span>
        )}
        <span className="ml-auto flex flex-wrap gap-1.5">
          {card.sources.map((s) => (
            <SourcePill key={s.id} source={s} compact />
          ))}
        </span>
      </div>
    </Card>
  );
}

const CHECK_ICON = { doc: FileText, people: Users, ticket: SquareKanban };

function ChecklistRow({ item, onToggle, onOpen, disabled }: { item: ChecklistItem; onToggle: () => void; onOpen: () => void; disabled: boolean }) {
  const Icon = CHECK_ICON[item.kind];
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <button
        type="button"
        role="checkbox"
        aria-checked={item.done}
        aria-label={item.label}
        disabled={disabled}
        onClick={onToggle}
        className={cn(
          "mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border transition-colors",
          item.done ? "border-foreground bg-foreground text-background" : "bg-card hover:border-foreground/40",
        )}
      >
        {item.done ? <Check className="size-3" /> : null}
      </button>
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm", item.done && "text-muted-foreground line-through decoration-muted-foreground/40")}>{item.label}</p>
        {item.note ? <p className="text-xs text-warn">{item.note}</p> : null}
      </div>
      {item.targetId ? (
        <button type="button" onClick={onOpen} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <Icon className="size-3.5" /> Open
        </button>
      ) : null}
    </div>
  );
}
