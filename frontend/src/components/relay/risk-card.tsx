"use client";

import { forwardRef, useState } from "react";
import useSWR from "swr";
import { Check, ChevronDown, CircleCheck, Lightbulb, Undo2, UserRound, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { PersonRow, RiskItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Avatar, Mono, SourcePill, StateBadge, TypeIcon, formatDay } from "./primitives";
import { renderCode } from "./source-drawer";

const BORDER: Record<string, string> = {
  at_risk: "border-l-risk",
  assigned: "border-l-risk",
  blocked: "border-l-risk",
  captured: "border-l-brand",
  verified: "border-l-covered",
  dismissed: "border-l-border",
};

const QUICK_REASONS = ["Out of date: the fix shipped", "A current doc covers this", "Someone else knows this", "Not important enough to hand over"];

interface Props {
  risk: RiskItem;
  leaverFirst: string;
  selected: boolean;
  canManage: boolean;
  onSelect: () => void;
  onAssign: (personId: string) => Promise<void>;
  onDismiss: (reason: string) => Promise<void>;
  onRestore: () => Promise<void>;
  onVerify: () => Promise<void>;
}

export const RiskCard = forwardRef<HTMLDivElement, Props>(function RiskCard(
  { risk, leaverFirst, selected, canManage, onSelect, onAssign, onDismiss, onRestore, onVerify },
  ref,
) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const ev = risk.evidence;
  const top = risk.suggestions[0];
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  };
  const obsolete = ev.facts.some((f) => f.startsWith("May be obsolete"));
  const dismissed = risk.state === "dismissed";
  const weak = ev.alternates.filter((a) => a.status !== "left");
  const former = ev.alternates.filter((a) => a.status === "left");

  return (
    <article
      ref={ref}
      tabIndex={-1}
      aria-label={`${risk.type}: ${risk.title}`}
      onClick={onSelect}
      className={cn(
        "rounded-2xl border border-l-[3px] bg-card p-5 transition-shadow transition-quiet",
        BORDER[risk.state],
        selected && "ring-2 ring-brand/30",
        dismissed && "bg-card/60",
      )}
    >
      <header className="flex items-start gap-3">
        <TypeIcon type={risk.type} className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3 className={cn("font-medium leading-snug", dismissed && "text-muted-foreground line-through decoration-muted-foreground/40")}>
            {risk.type === "System" ? <Mono className="text-[13.5px]">{risk.title}</Mono> : risk.title}
          </h3>
          {!dismissed && ev.facts[0] ? <p className="mt-0.5 text-muted-foreground">{ev.facts[0]}</p> : null}
        </div>
        <StateBadge state={risk.state} />
      </header>

      {dismissed ? (
        <div className="mt-2 flex items-center gap-2 pl-7 text-xs text-muted-foreground">
          <span>
            Dismissed{risk.dismissedBy ? ` by ${risk.dismissedBy}` : ""}: {risk.dismissReason ?? risk.note}
          </span>
          {canManage ? (
            <Button variant="ghost" size="xs" onClick={(e) => { e.stopPropagation(); run("restore", onRestore); }}>
              <Undo2 /> Restore
            </Button>
          ) : null}
        </div>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-1.5 pl-7">
            {ev.sources.slice(0, 3).map((s) => (
              <SourcePill key={s.id} source={s} compact />
            ))}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setExpanded((x) => !x); }}
              aria-expanded={expanded}
              className="ml-1 inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
            >
              Evidence <ChevronDown className={cn("size-3 transition-transform", expanded && "rotate-180")} />
            </button>
          </div>

          {expanded ? (
            <div className="mt-3 space-y-2 border-t pt-3 pl-7 text-sm" onClick={(e) => e.stopPropagation()}>
              <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
                {ev.facts.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
              <p className="text-xs text-muted-foreground">
                {weak.length
                  ? `Nobody else knows this well. Some people know a little: ${weak.map((a) => `${a.name} (${a.basis})`).join(", ")}.`
                  : "Nobody else knows this."}
                {former.length ? ` ${former.map((a) => `${a.name} also knew it, but ${a.note}`).join(". ")}.` : ""}
              </p>
              {ev.sources.length > 3 ? (
                <div className="flex flex-wrap gap-1.5">
                  {ev.sources.slice(3).map((s) => (
                    <SourcePill key={s.id} source={s} compact />
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {obsolete && risk.state === "at_risk" ? (
            <p className="mt-3 flex items-center gap-1.5 pl-7 text-xs text-muted-foreground">
              <Lightbulb className="size-3.5" aria-hidden /> A later ticket says the fix shipped. If you no longer need this, dismiss it.
            </p>
          ) : null}

          {risk.knowledge ? (
            <div className="mt-3 ml-7 rounded-xl bg-background px-3.5 py-2.5 text-sm" onClick={(e) => e.stopPropagation()}>
              <p className="mb-1 text-xs text-muted-foreground">
                {leaverFirst} answered · {formatDay(risk.knowledge.capturedAt)}
                {risk.knowledge.verifiedAt ? ` · verified by ${risk.knowledge.verifiedBy}` : ""}
              </p>
              <p className="line-clamp-3 leading-relaxed">{renderCode(risk.knowledge.answer)}</p>
            </div>
          ) : null}

          <footer className="mt-3 flex flex-wrap items-center gap-2 pl-7" onClick={(e) => e.stopPropagation()}>
            {risk.successor ? (
              <span className="inline-flex min-w-0 items-center gap-2 text-sm">
                <Avatar name={risk.successor.name} size={20} />
                <span className="truncate">
                  <span className="text-muted-foreground">Next owner </span>
                  <span className="font-medium">{risk.successor.name}</span>
                </span>
              </span>
            ) : top ? (
              <span className="inline-flex min-w-0 flex-1 items-center gap-2 text-sm">
                <Avatar name={top.name} size={20} />
                <span className="min-w-0">
                  <span className="text-muted-foreground">Suggested </span>
                  <span className="font-medium">{top.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">{top.reason}</span>
                </span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                <UserRound className="size-4" /> No clear next owner. Choose someone.
              </span>
            )}
            {canManage ? (
              <div className="ml-auto flex items-center gap-1.5">
                {!risk.successor && top ? (
                  <Button size="sm" onClick={() => run("assign", () => onAssign(top.id))} disabled={!!busy}>
                    <Check /> {busy === "assign" ? "Assigning…" : "Accept"}
                  </Button>
                ) : null}
                <ChangeSuccessor risk={risk} onPick={(id) => run("assign", () => onAssign(id))} label={risk.successor || !top ? "Choose" : "Change"} />
                {risk.state === "captured" ? (
                  <Button size="sm" variant="outline" onClick={() => run("verify", onVerify)} disabled={!!busy || !risk.successor} title={!risk.successor ? "Assign a next owner first" : undefined}>
                    <CircleCheck /> {busy === "verify" ? "Verifying…" : "Verify"}
                  </Button>
                ) : null}
                <DismissButton onDismiss={(r) => run("dismiss", () => onDismiss(r))} suggested={obsolete ? QUICK_REASONS[0] : undefined} />
              </div>
            ) : null}
          </footer>
        </>
      )}
    </article>
  );
});

function ChangeSuccessor({ risk, onPick, label }: { risk: RiskItem; onPick: (id: string) => void; label: string }) {
  const [open, setOpen] = useState(false);
  const { data: people } = useSWR<PersonRow[]>(open ? "/api/people" : null);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost">
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-2">
        <p className="px-2 pb-1 pt-1 text-xs font-medium text-muted-foreground">Suggested from the graph</p>
        <ul>
          {risk.suggestions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => {
                  onPick(s.id);
                  setOpen(false);
                }}
                className="flex w-full items-start gap-2 rounded-md px-2 py-2 text-left hover:bg-secondary"
              >
                <Avatar name={s.name} size={22} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    {s.name}
                    <span className="text-[11px] font-normal text-muted-foreground">{s.confidence} confidence</span>
                  </span>
                  <span className="block text-xs text-muted-foreground">{s.reason}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-1 border-t px-2 pt-2">
          <p className="pb-1 text-xs font-medium text-muted-foreground">Someone else</p>
          <Select onValueChange={(v) => { onPick(v); setOpen(false); }}>
            <SelectTrigger className="w-full" size="sm">
              <SelectValue placeholder="Pick a teammate" />
            </SelectTrigger>
            <SelectContent>
              {(people ?? [])
                .filter((p) => p.status === "active" && !p.lastDay)
                .map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name} · {p.team}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <p className="pt-2 text-[11px] text-muted-foreground">Stays at risk until the answer is verified.</p>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function DismissButton({ onDismiss, suggested }: { onDismiss: (reason: string) => void; suggested?: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(suggested ?? "");
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (o) setReason(suggested ?? ""); }}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost" aria-label="Dismiss">
          <X /> Dismiss
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <p className="text-sm font-medium">Dismiss as a false alarm?</p>
        <p className="mt-0.5 text-xs text-muted-foreground">Relay keeps your reason and stops flagging it.</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {QUICK_REASONS.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setReason(r)}
              className={cn("rounded-full border px-2 py-0.5 text-xs", reason === r ? "border-foreground/30 bg-secondary" : "text-muted-foreground")}
            >
              {r}
            </button>
          ))}
        </div>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this not a real risk?" className="mt-2 min-h-16 text-sm" />
        <div className="mt-3 flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={() => {
              onDismiss(reason);
              setOpen(false);
            }}
          >
            Dismiss
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
