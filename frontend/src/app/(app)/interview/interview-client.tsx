"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Check, Mic } from "lucide-react";

import { useApp, useCompany } from "@/components/app-provider";
import { EmptyState, Mono, PageHeader, Skeleton, SourcePill, TypeIcon, formatDay } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, enc } from "@/lib/api";
import type { HandoverSummary, Interview } from "@/lib/types";
import { cn } from "@/lib/utils";

const DRAFT = (rid: string) => `baton.draft.${rid}`;

function readDraft(rid: string) {
  try {
    return localStorage.getItem(DRAFT(rid)) ?? "";
  } catch {
    return "";
  }
}
function writeDraft(rid: string, v: string) {
  try {
    if (v) localStorage.setItem(DRAFT(rid), v);
    else localStorage.removeItem(DRAFT(rid));
  } catch {
    /* storage unavailable: the server copy is the source of truth */
  }
}

export function InterviewClient() {
  const company = useCompany();
  const { persona, personaInfo } = useApp();
  const { data: list } = useSWR<HandoverSummary[]>("/api/handovers");
  const mine = list?.find((h) => h.leaver.id === persona && h.status !== "closed") ?? list?.find((h) => h.status !== "closed");
  const viewingOwn = !!mine && mine.leaver.id === persona;
  const { data, mutate } = useSWR<Interview>(mine ? `/api/handovers/${mine.id}/interview` : null);
  const [index, setIndex] = useState<number | null>(null);
  const [started, setStarted] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  const q = data && index !== null ? data.questions[index] : null;

  useEffect(() => {
    if (q) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setText(q.answer ?? readDraft(q.riskId));
      requestAnimationFrame(() => area.current?.focus());
    }
  }, [q?.riskId, q?.answer]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = useMemo(() => (data ? data.questions.filter((x) => x.answer).length : 0), [data]);

  if (!list) return <Shell><Skeleton className="h-64" /></Shell>;
  if (!mine) {
    return (
      <Shell>
        <EmptyState title="No handover in progress" body="Your questions show up here when a handover starts." />
      </Shell>
    );
  }
  if (!data) return <Shell><Skeleton className="h-64" /></Shell>;

  const first = data.leaver.name.split(" ")[0];
  const total = data.questions.length;

  const go = (i: number | null) => setIndex(i);
  const nextOpen = (from: number) => {
    for (let i = from + 1; i < total; i++) if (!data.questions[i].answer && !data.questions[i].skipped) return i;
    for (let i = 0; i < total; i++) if (!data.questions[i].answer && !data.questions[i].skipped) return i;
    return null;
  };

  const save = async () => {
    if (!q || !text.trim()) return;
    if (!viewingOwn) {
      toast("Preview only", { description: `To answer, choose ${first} under View as.` });
      return;
    }
    setSaving(true);
    try {
      await api.post(`/api/handovers/${data.handover.id}/answers`, { riskItemId: q.riskId, answerText: text.trim() });
      writeDraft(q.riskId, "");
      const fresh = await mutate();
      const nx = fresh ? (() => {
        for (let i = index! + 1; i < fresh.questions.length; i++) if (!fresh.questions[i].answer && !fresh.questions[i].skipped) return i;
        return fresh.questions.findIndex((x) => !x.answer && !x.skipped);
      })() : null;
      go(nx === -1 || nx === null ? -1 : nx);
    } catch (e) {
      toast.error("Answer not saved", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  };

  const skip = async () => {
    if (!q) return;
    if (viewingOwn) await api.post(`/api/handovers/${data.handover.id}/risks/${enc(q.riskId)}/skip`).catch(() => null);
    await mutate();
    const nx = nextOpen(index!);
    go(nx === null ? -1 : nx);
  };

  // ------------------------------------------------------------- intro
  if (!started && index === null) {
    return (
      <Shell>
        {!viewingOwn ? <PreviewNote name={first} /> : null}
        <PageHeader
          eyebrow={`Your handover · last day ${formatDay(data.handover.lastDay, { weekday: "long", day: "numeric", month: "long" })}`}
          title={`Help keep what you know, ${first}.`}
          subtitle={`${total} short questions about work only you know well.`}
        />
        <ul className="mt-6 space-y-1.5 text-[14px] text-muted-foreground">
          <li>A few sentences per answer is enough.</li>
          <li>Answers save as you go. Skip anything.</li>
          <li>{data.joiner ? `${data.joiner.name.split(" ")[0]} sees your answers on Day One.` : "Your next owners see your answers."}</li>
        </ul>
        <div className="mt-8 flex items-center gap-3">
          <Button size="lg" onClick={() => { setStarted(true); const nx = data.progress.next; go(nx === null ? -1 : nx); }}>
            {done ? `Continue (${done} of ${total} done)` : "Start"} <ArrowRight />
          </Button>
          <span className="text-sm text-muted-foreground">About 30 minutes in total</span>
        </div>
      </Shell>
    );
  }

  // ---------------------------------------------------------------- end
  if (index === -1 || (started && index === null)) {
    const skipped = data.questions.filter((x) => x.skipped && !x.answer).length;
    return (
      <Shell>
        <div className="flex size-10 items-center justify-center rounded-full bg-covered-soft text-covered">
          <Check className="size-5" />
        </div>
        <PageHeader
          className="mt-4"
          title={`Thank you, ${first}.`}
          subtitle={`You passed on ${done} thing${done === 1 ? "" : "s"} only you knew.${data.joiner ? ` ${data.joiner.name.split(" ")[0]} sees them on Day One.` : ""}`}
        />
        {skipped ? <p className="mt-3 text-sm text-muted-foreground">{skipped} skipped. Your manager can find another owner.</p> : null}
        <div className="mt-8 flex gap-2">
          <Button variant="outline" onClick={() => go(0)}>
            Review answers
          </Button>
        </div>
      </Shell>
    );
  }

  if (!q) return null;
  const pct = Math.round((done / total) * 100);
  return (
    <Shell wide>
      {!viewingOwn ? <PreviewNote name={first} /> : null}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="tabular">
          {index! + 1} of {total}
        </span>
        <span className="tabular">{done} answered</span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total} aria-label="Answered">
        <div className="h-full rounded-full bg-foreground/70 transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>

      <div key={q.riskId} className="mt-10 animate-in fade-in slide-in-from-bottom-1 duration-300">
        <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <TypeIcon type={q.type} className="size-3.5" /> {q.type === "System" ? <Mono>{q.title}</Mono> : q.title}
        </p>
        <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
          {q.context} {q.source ? <SourcePill source={q.source} compact className="ml-1" /> : null}
        </p>
        <h1 className="mt-4 text-[22px] font-semibold leading-snug tracking-tight">{q.prompt}</h1>
        <textarea
          ref={area}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            writeDraft(q.riskId, e.target.value);
          }}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") save();
          }}
          rows={7}
          placeholder="Type your answer…"
          aria-label={q.prompt}
          className="mt-6 w-full resize-y rounded-xl border bg-card p-4 text-[15px] leading-relaxed outline-none transition-shadow focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => go(Math.max(0, index! - 1))} disabled={index === 0}>
            <ArrowLeft /> Back
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button variant="ghost" size="icon-sm" disabled aria-label="Answer by voice (coming later)">
                  <Mic />
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>Voice answers are coming later</TooltipContent>
          </Tooltip>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-xs text-muted-foreground sm:inline">{text && !q.answer ? "Draft saved" : ""}</span>
            <Button variant="ghost" onClick={skip}>
              Skip
            </Button>
            <Button onClick={save} disabled={!text.trim() || saving}>
              {saving ? "Saving…" : q.answer ? "Update & next" : "Save & next"} <kbd className="ml-1 hidden rounded border border-white/30 px-1 text-[10px] sm:inline">⌘↵</kbd>
            </Button>
          </div>
        </div>
      </div>

      <nav aria-label="Questions" className="mt-12 flex flex-wrap gap-1.5">
        {data.questions.map((x, i) => (
          <button
            key={x.riskId}
            type="button"
            onClick={() => go(i)}
            aria-label={`Question ${i + 1}: ${x.title}${x.answer ? " (answered)" : x.skipped ? " (skipped)" : ""}`}
            aria-current={i === index ? "step" : undefined}
            className={cn(
              "h-1.5 w-6 rounded-full transition-colors",
              x.answer ? "bg-foreground/70" : x.skipped ? "bg-muted-foreground/30" : "bg-secondary",
              i === index && "ring-2 ring-brand/40 ring-offset-2 ring-offset-background",
            )}
          />
        ))}
      </nav>
      <p className="mt-6 text-xs text-muted-foreground">
        Questions come from {company}&apos;s work tools only.{" "}
        {personaInfo && !viewingOwn ? <Link href="/home" className="underline">Back to home</Link> : null}
      </p>
    </Shell>
  );
}

function Shell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return <div className={cn("mx-auto px-4 py-14 md:px-8", wide ? "max-w-[720px]" : "max-w-[640px]")}>{children}</div>;
}

function PreviewNote({ name }: { name: string }) {
  return <p className="mb-6 rounded-xl border bg-card px-3 py-2 text-xs text-muted-foreground">Preview of {name}&apos;s questions. Switch to {name} under View as to answer.</p>;
}
