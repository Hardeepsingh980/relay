"use client";

import useSWR from "swr";
import { ExternalLink, Info } from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useApp } from "@/components/app-provider";
import { fetcher, sourcePath } from "@/lib/api";
import type { SourceDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Avatar, Mono, Skeleton, formatDay } from "./primitives";

const KIND_NAME: Record<string, string> = {
  slack: "Slack thread",
  doc: "Document",
  jira: "Jira ticket",
  meeting: "Meeting transcript",
  github: "GitHub",
  handover: "Handover answer",
  support: "Support ticket",
  crm: "HubSpot record",
  conversation: "Customer conversation",
  roadmap: "Roadmap item",
  promise: "Promise",
};

function time(iso?: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
}

export function SourceDrawer() {
  const { source, closeSource } = useApp();
  const key = source ? sourcePath(source.nodeLabel || "Message", source.id) : null;
  const { data, error, isLoading } = useSWR<SourceDetail>(key, fetcher);

  return (
    <Sheet open={!!source} onOpenChange={(o) => !o && closeSource()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[520px]">
        <SheetHeader className="border-b px-5 py-4">
          <p className="text-xs font-medium text-muted-foreground">{source ? KIND_NAME[source.kind] ?? "Source" : ""}</p>
          <SheetTitle className="pr-8 text-[16px] leading-snug">{source?.title}</SheetTitle>
          <SheetDescription className="text-xs">{data?.at ? time(data.at) : source?.at ? time(source.at) : ""}</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : error ? (
            <Unavailable text="This source did not open." />
          ) : data ? (
            <Body d={data} highlight={source?.highlight ?? null} />
          ) : null}
        </div>
        {data && ((data.url && !/\.example\b/.test(data.url)) || (data.availability && !/\b(demo|sample)\b/i.test(data.availability))) ? (
          <div className="flex items-start gap-2 border-t bg-secondary/50 px-5 py-3 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <div>
              {data.availability && !/\b(demo|sample)\b/i.test(data.availability) ? <p>{data.availability}</p> : null}
              {data.url && !/\.example\b/.test(data.url) ? (
                <p className="mt-1 inline-flex items-center gap-1 opacity-70">
                  <ExternalLink className="size-3" aria-hidden />
                  <span className="truncate">{data.url}</span>
                  <span className="sr-only">(not a live link)</span>
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Unavailable({ text }: { text: string }) {
  return <p className="rounded-md border border-dashed p-4 text-muted-foreground">{text}</p>;
}

function Body({ d, highlight }: { d: SourceDetail; highlight: string | null }) {
  if (d.thread) {
    return (
      <ol className="space-y-4">
        {d.thread.map((m) => (
          <li
            key={m.id}
            className={cn(
              "rounded-lg p-3 -mx-3",
              (m.focus || (highlight && m.author === highlight)) && "bg-brand-soft/70 ring-1 ring-brand/20",
            )}
            aria-current={m.focus ? "true" : undefined}
          >
            <div className="mb-1 flex items-center gap-2">
              <Avatar name={m.author} size={22} />
              <span className="font-medium">{m.author}</span>
              {m.external ? <span className="rounded-full border px-1.5 text-[10px] text-muted-foreground">{m.org}</span> : null}
              <span className="text-xs text-muted-foreground tabular">{time(m.at)}</span>
            </div>
            <p className="whitespace-pre-wrap pl-[30px] leading-relaxed">{renderCode(m.text)}</p>
          </li>
        ))}
      </ol>
    );
  }
  if (d.transcript) {
    return (
      <div className="space-y-4">
        {d.notes ? <p className="rounded-md bg-secondary px-3 py-2 text-xs text-muted-foreground">Notes: {d.notes}</p> : null}
        <ol className="space-y-3">
          {d.transcript.map((t, i) => (
            <li
              key={i}
              className={cn("-mx-2 grid grid-cols-[110px_1fr] gap-3 rounded-md px-2 py-1", highlight && t.speaker === highlight && "bg-brand-soft/70")}
            >
              <span className="truncate pt-px text-xs font-medium text-muted-foreground">{t.speaker}</span>
              <span className="leading-relaxed">{t.text}</span>
            </li>
          ))}
        </ol>
      </div>
    );
  }
  if (d.body !== undefined) {
    return (
      <div className="space-y-3">
        {d.freshness === "stale" || d.freshness === "aging" ? (
          <p className="rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
            {d.freshness === "stale" ? "Out of date" : "Not updated recently"}: {d.staleReason}
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {d.author ? `By ${d.author}${d.authorStatus === "left" ? " (left the company)" : ""} · ` : ""}Updated {formatDay(d.updatedAt, { year: "numeric" })}
        </p>
        <div className="prose-sm space-y-2 whitespace-pre-wrap leading-relaxed">{renderMarkdownish(d.body ?? "")}</div>
      </div>
    );
  }
  if (d.comments !== undefined) {
    return (
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {d.status} · {d.assignee ? `Assigned to ${d.assignee}` : "Unassigned"}
        </p>
        <p className="leading-relaxed">{d.description}</p>
        {d.comments.length ? (
          <ul className="space-y-2 border-t pt-3">
            {d.comments.map((c, i) => (
              <li key={i} className="text-sm">
                <span className="text-xs text-muted-foreground">{time(c.created)} · </span>
                {c.body}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  if (d.answer) {
    return (
      <div className="space-y-3">
        <p className="text-xs font-medium text-muted-foreground">{d.question}</p>
        <p className="whitespace-pre-wrap leading-relaxed">{renderCode(d.answer)}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {d.repo ? <Mono className="text-muted-foreground">{d.repo}</Mono> : null}
      <p className="leading-relaxed">{d.message ?? d.excerpt}</p>
      {d.author ? <p className="text-xs text-muted-foreground">by {d.author}</p> : null}
    </div>
  );
}

export function renderCode(text: string) {
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((p, i) =>
    p.startsWith("`") && p.endsWith("`") ? (
      <code key={i} className="rounded bg-secondary px-1 py-0.5 font-mono text-[12px]">
        {p.slice(1, -1)}
      </code>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

function renderMarkdownish(md: string) {
  return md.split("\n").map((line, i) => {
    if (line.startsWith("# ")) return <p key={i} className="text-[15px] font-semibold">{line.slice(2)}</p>;
    if (line.startsWith("## ")) return <p key={i} className="pt-2 font-semibold">{line.slice(3)}</p>;
    if (/^\s*[-\d]+[.)]?\s/.test(line)) return <p key={i} className="pl-3">{renderCode(line)}</p>;
    if (!line.trim()) return <span key={i} className="block h-1" />;
    return <p key={i}>{renderCode(line)}</p>;
  });
}
