"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, ChevronDown, CornerDownLeft, Search, TriangleAlert } from "lucide-react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useApp } from "@/components/app-provider";
import { api } from "@/lib/api";
import type { AskAnswer, PathStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SourcePill, kindForLabel } from "./primitives";
import { renderCode } from "./source-drawer";

export const EXAMPLES = [
  "Why does the settlement job run at 2 AM?",
  "Why do we keep idempotency keys for 72 hours?",
  "How do I fix a settlement “lock held” failure?",
  "Who else understands reconciliation-service?",
];

const STEPS = ["Finding the systems and customers in your question…", "Searching past decisions, chats and handover answers…", "Following the links in the graph…"];

export function useAsk() {
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [asked, setAsked] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const ask = async (q: string) => {
    const question = q.trim();
    if (!question) return;
    setAsked(question);
    setLoading(true);
    setError(null);
    setAnswer(null);
    setStep(0);
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 450);
    try {
      setAnswer(await api.post<AskAnswer>("/api/ask", { question }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The request failed");
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  };
  return { answer, asked, loading, step, error, ask, reset: () => { setAnswer(null); setAsked(""); } };
}

export function AskBar() {
  const { askOpen, askSeed, closeAsk } = useApp();
  const [q, setQ] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const a = useAsk();

  useEffect(() => {
    if (askOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setQ(askSeed);
      if (askSeed) a.ask(askSeed);
      else a.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askOpen, askSeed]);

  return (
    <Dialog open={askOpen} onOpenChange={(o) => !o && closeAsk()}>
      <DialogContent
        showCloseButton={false}
        className="top-[12vh] max-w-[680px] translate-y-0 gap-0 overflow-hidden p-0 shadow-float sm:max-w-[680px]"
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          input.current?.focus();
        }}
      >
        <DialogTitle className="sr-only">Ask Relay</DialogTitle>
        <form
          className="flex items-center gap-3 border-b px-4"
          onSubmit={(e) => {
            e.preventDefault();
            a.ask(q);
          }}
        >
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            ref={input}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask why something works the way it does…"
            aria-label="Ask a question"
            className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground focus-visible:outline-none"
          />
          <kbd className="hidden rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground sm:inline">esc</kbd>
        </form>
        <div className="max-h-[62vh] overflow-y-auto">
          <AskResult a={a} onAsk={(x) => { setQ(x); a.ask(x); }} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AskResult({ a, onAsk, examples }: { a: ReturnType<typeof useAsk>; onAsk: (q: string) => void; examples?: string[] }) {
  const { session } = useApp();
  examples = examples ?? session?.suggestions ?? EXAMPLES;
  if (a.loading) {
    return (
      <div className="space-y-2 px-5 py-5" aria-live="polite">
        {STEPS.slice(0, a.step + 1).map((s, i) => (
          <p key={s} className={cn("text-sm", i === a.step ? "text-foreground" : "text-muted-foreground")}>
            {s}
          </p>
        ))}
      </div>
    );
  }
  if (a.error) return <p className="px-5 py-5 text-sm text-muted-foreground">Relay did not answer: {a.error}</p>;
  if (!a.answer) {
    return (
      <div className="px-5 py-4">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Try asking</p>
        <ul className="space-y-0.5">
          {examples.map((ex) => (
            <li key={ex}>
              <button
                type="button"
                onClick={() => onAsk(ex)}
                className="group flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-sm hover:bg-secondary"
              >
                {ex}
                <CornerDownLeft className="size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return <AnswerView answer={a.answer} onAsk={onAsk} />;
}

function modeLabel(a: AskAnswer) {
  if (a.mode === "graph") return "Answered from the graph";
  if (a.mode === "llm") return `Written from ${a.sources.length} source${a.sources.length === 1 ? "" : "s"}`;
  if (a.mode === "extractive") return `Quoted from ${a.sources.length} source${a.sources.length === 1 ? "" : "s"}`;
  return "No answer in the sources";
}

export function AnswerView({ answer, onAsk }: { answer: AskAnswer; onAsk: (q: string) => void }) {
  const [open, setOpen] = useState(false);
  const byTag = Object.fromEntries(answer.sources.map((s) => [s.tag, s]));
  return (
    <div className="px-5 py-5" aria-live="polite">
      <p className="text-[15px] leading-relaxed">
        {answer.segments.map((seg, i) =>
          "text" in seg ? (
            <span key={i}>{renderCode(seg.text)}</span>
          ) : byTag[seg.source] ? (
            <SourcePill key={i} source={byTag[seg.source]} compact className="mx-0.5" />
          ) : null,
        )}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{modeLabel(answer)}</span>
        {answer.freshness?.label ? <span>Newest source {answer.freshness.label}</span> : null}
        {answer.mode === "extractive" ? <span>Offline mode: no AI model is connected</span> : null}
      </div>
      {answer.conflicts.map((c, i) => (
        <div key={i} className="mt-3 flex items-start gap-2 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span className="flex-1">{c.note}</span>
          <SourcePill source={c.source} compact />
        </div>
      ))}
      {answer.path.length > 1 ? (
        <div className="mt-4 border-t pt-3">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
            How I found this
          </button>
          {open ? <PathTrace path={answer.path} /> : <PathTrace path={answer.path} compact />}
        </div>
      ) : null}
      {answer.followups.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {answer.followups.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => onAsk(f)}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-foreground/25 hover:text-foreground"
            >
              {f}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const STEP_STYLE: Record<string, string> = {
  question: "bg-secondary",
  system: "rounded-[4px] border",
  customer: "border",
  decision: "border border-brand/40 bg-brand-soft",
  workaround: "border",
  person: "rounded-full border",
  handover: "border border-brand/40 bg-brand-soft",
  bug: "border border-warn/40 bg-warn-soft",
  ticket: "border",
  roadmap: "border border-brand/40 bg-brand-soft",
  message: "border",
  promise: "border border-warn/40 bg-warn-soft",
};

export function PathTrace({ path, compact }: { path: PathStep[]; compact?: boolean }) {
  const { openSource } = useApp();
  const steps = compact ? path.slice(1) : path;
  return (
    <ol className={cn("mt-2 flex flex-wrap items-center gap-y-2 text-xs", compact && "opacity-80")} aria-label="Path through the graph">
      {steps.map((p, i) => {
        const clickable = p.nodeLabel && p.id;
        const body = (
          <span className={cn("inline-flex max-w-[16rem] items-center gap-1 rounded-md px-2 py-1", STEP_STYLE[p.kind] ?? "border")}>
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{p.kind === "slack" || p.kind === "meeting" || p.kind === "doc" || p.kind === "github" ? p.kind : p.kind}</span>
            <span className="truncate">{p.label}</span>
          </span>
        );
        return (
          <li key={i} className="flex items-center">
            {i > 0 ? (
              <span className="mx-1.5 inline-flex items-center gap-1 text-muted-foreground">
                {!compact && p.edge ? <span className="text-[10px]">{p.edge}</span> : null}
                <ArrowRight className="size-3" aria-hidden />
              </span>
            ) : null}
            {clickable ? (
              <button
                type="button"
                onClick={() => openSource({ kind: kindForLabel(p.nodeLabel, p.kind), id: p.id!, nodeLabel: p.nodeLabel!, title: p.label, label: p.label })}
                className="hover:opacity-80"
              >
                {body}
              </button>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ol>
  );
}
