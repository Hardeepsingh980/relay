"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CalendarPlus, FileDiff, Mail, MoveRight, SquareKanban, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import type { Action, DocProposal } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card, Mono, SectionTitle } from "./primitives";

const ICON: Record<Action["type"], LucideIcon> = {
  "calendar.intro": CalendarPlus,
  "ticket.reassign": SquareKanban,
  "email.draft": Mail,
};

export function ActionStatus({ a }: { a: Action }) {
  const map: Record<string, { label: string; cls: string }> = {
    proposed: { label: "Needs review", cls: "text-muted-foreground" },
    running: { label: "Running…", cls: "text-muted-foreground" },
    succeeded: { label: "Done", cls: "text-covered" },
    simulated: { label: "Saved in Relay", cls: "text-muted-foreground" },
    failed: { label: "Failed", cls: "text-risk" },
  };
  const m = map[a.status];
  return <span className={cn("text-xs", m.cls)}>{m.label}</span>;
}

export function ActionReview({ action, open, onOpenChange, onDone }: { action: Action; open: boolean; onOpenChange: (o: boolean) => void; onDone: (a: Action) => void }) {
  const [busy, setBusy] = useState(false);
  const p = action.payload as Record<string, string | string[] | number>;
  const approve = async () => {
    setBusy(true);
    try {
      const done = await api.post<Action>(`/api/actions/${action.id}/approve`, {});
      onDone(done);
      if (done.status === "failed") toast.error("Action failed", { description: done.result?.message });
      else toast.success(done.status === "simulated" ? "Saved in Relay" : "Done", { description: done.result?.message });
    } catch (e) {
      toast.error("The action did not run", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  };
  const done = action.status !== "proposed" && action.status !== "failed";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{action.title}</DialogTitle>
          <DialogDescription>
            Destination: {action.destination} ·{" "}
            {action.mode === "live" ? "Runs in the connected tool" : "Saved in Relay. No outside tool changes."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 rounded-xl border bg-background p-3 text-sm">
          {action.type === "ticket.reassign" ? (
            <>
              <p>
                <Mono>{String(p.ticketKey)}</Mono> · {String(p.title)}
              </p>
              <p className="flex items-center gap-2">
                {String(p.fromName)} <MoveRight className="size-3.5 text-muted-foreground" /> <span className="font-medium">{String(p.toName)}</span>
              </p>
              <p className="text-muted-foreground">Comment: {String(p.comment)}</p>
            </>
          ) : action.type === "email.draft" ? (
            <>
              <p className="text-xs text-muted-foreground">To: {(p.to as string[]).join(", ")} · Cc: {(p.cc as string[]).join(", ")}</p>
              <p className="font-medium">{String(p.subject)}</p>
              <p className="whitespace-pre-wrap leading-relaxed">{String(p.body)}</p>
              <p className="text-xs text-muted-foreground">Saved as a draft. Sending needs a second approval.</p>
            </>
          ) : (
            <>
              <p className="font-medium">{String(p.title)}</p>
              <p>
                {new Date(String(p.start)).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST · {String(p.durationMinutes)} minutes
              </p>
              <p className="text-muted-foreground">Invitees: {(p.attendeeNames as string[]).join(", ")}</p>
            </>
          )}
        </div>
        {action.result ? (
          <p className={cn("rounded-xl px-3 py-2 text-sm", action.status === "failed" ? "bg-risk-soft text-risk" : "bg-secondary")}>
            {action.result.message}
            {action.result.url ? (
              <>
                {" "}
                <a href={action.result.url} target="_blank" rel="noreferrer" className="text-primary underline-offset-2 hover:underline">
                  Open
                </a>
              </>
            ) : null}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {done ? "Close" : "Cancel"}
          </Button>
          {!done ? (
            <Button onClick={approve} disabled={busy}>
              {busy ? "Running…" : action.status === "failed" ? "Retry" : action.mode === "live" ? "Approve and run" : "Approve"}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ActionsPanel({ handoverId, canManage, version }: { handoverId: string; canManage: boolean; version: string }) {
  const { data, mutate } = useSWR<Action[]>(`/api/handovers/${handoverId}/actions?v=${version}`, { keepPreviousData: true });
  const [review, setReview] = useState<Action | null>(null);
  return (
    <section>
      <SectionTitle count={data?.length}>Follow-up actions</SectionTitle>
      {!data?.length ? (
        <p className="text-sm text-muted-foreground">Accept next owners to prepare ticket moves and intros.</p>
      ) : (
        <Card className="divide-y">
          {data.map((a) => {
            const Icon = ICON[a.type];
            return (
              <div key={a.id} className="flex items-center gap-3 px-4 py-3">
                <Icon className="size-4 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{a.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {a.destination} · <ActionStatus a={a} />
                  </p>
                </div>
                <Button size="sm" variant={a.status === "proposed" ? "outline" : "ghost"} onClick={() => setReview(a)} disabled={!canManage && a.status === "proposed"}>
                  {a.status === "proposed" ? "Review" : "Details"}
                </Button>
              </div>
            );
          })}
        </Card>
      )}
      {review ? (
        <ActionReview
          action={review}
          open
          onOpenChange={(o) => !o && setReview(null)}
          onDone={(a) => {
            setReview(a);
            mutate();
          }}
        />
      ) : null}
    </section>
  );
}

export function DocProposals({ handoverId, canManage, version }: { handoverId: string; canManage: boolean; version: string }) {
  const { data, mutate } = useSWR<DocProposal[]>(`/api/handovers/${handoverId}/doc-proposals?v=${version}`, { keepPreviousData: true });
  const [open, setOpen] = useState<DocProposal | null>(null);
  if (!data?.length) return null;
  return (
    <section>
      <SectionTitle count={data.length}>Docs to update</SectionTitle>
      <Card className="divide-y">
        {data.map((d) => (
          <div key={d.id} className="flex items-center gap-3 px-4 py-3">
            <FileDiff className="size-4 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{d.title}</p>
              <p className="text-xs text-muted-foreground">{d.status === "applied" ? `Updated by ${d.approvedBy}` : d.summary}</p>
            </div>
            <Button size="sm" variant={d.status === "proposed" ? "outline" : "ghost"} onClick={() => setOpen(d)}>
              {d.status === "proposed" ? "Review changes" : "View"}
            </Button>
          </div>
        ))}
      </Card>
      {open ? (
        <Dialog open onOpenChange={(o) => !o && setOpen(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Update “{open.title}”</DialogTitle>
              <DialogDescription>
                Written from the handover answers{open.mode === "template" ? ", word for word" : ""}. Nothing changes until you approve.
              </DialogDescription>
            </DialogHeader>
            <pre className="max-h-[50vh] overflow-auto rounded-xl border bg-background p-3 font-mono text-[12px] leading-relaxed">
              {open.diff.split("\n").map((l, i) => (
                <span
                  key={i}
                  className={cn(
                    "block whitespace-pre-wrap",
                    l.startsWith("+") && !l.startsWith("+++") && "bg-covered-soft text-covered",
                    l.startsWith("-") && !l.startsWith("---") && "bg-risk-soft text-risk",
                    l.startsWith("@@") && "text-muted-foreground",
                  )}
                >
                  {l || " "}
                </span>
              ))}
            </pre>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setOpen(null)}>
                Close
              </Button>
              {open.status === "proposed" && canManage ? (
                <Button
                  onClick={async () => {
                    await api.post(`/api/doc-proposals/${open.id}/approve`);
                    toast.success("Doc updated", { description: "Saved in Relay." });
                    setOpen(null);
                    mutate();
                  }}
                >
                  Approve update
                </Button>
              ) : null}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}
