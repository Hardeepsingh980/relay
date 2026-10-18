"use client";

import {
  Boxes,
  Building2,
  Contact,
  FileText,
  GitCommitHorizontal,
  Handshake,
  Hash,
  LifeBuoy,
  Map,
  MessageSquareText,
  MessagesSquare,
  Split,
  SquareKanban,
  Video,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ItemType, RiskState, SourceKind, SourceRef } from "@/lib/types";
import { useApp } from "@/components/app-provider";

/* ---------------------------------------------------------------- avatar */

export function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
}

const AVATAR_TINTS = ["bg-blush", "bg-lavender", "bg-mint", "bg-powder", "bg-butter"];

export function Avatar({ name, size = 24, className, ring }: { name: string; size?: number; className?: string; ring?: "risk" | "brand" }) {
  const tint = AVATAR_TINTS[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_TINTS.length];
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center rounded-full font-medium text-foreground/80",
        tint,
        ring === "risk" && "ring-2 ring-risk/50 ring-offset-1 ring-offset-card",
        ring === "brand" && "ring-2 ring-brand/40 ring-offset-1 ring-offset-card",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.38)) }}
    >
      {initials(name)}
    </span>
  );
}

export function PersonChip({ name, role, size = 24 }: { name: string; role?: string | null; size?: number }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <Avatar name={name} size={size} />
      <span className="min-w-0">
        <span className="block truncate font-medium leading-tight">{name}</span>
        {role ? <span className="block truncate text-xs text-muted-foreground leading-tight">{role}</span> : null}
      </span>
    </span>
  );
}

/* ------------------------------------------------------------ type icons */

export const TYPE_META: Record<ItemType, { icon: LucideIcon; label: string; plural: string }> = {
  System: { icon: Boxes, label: "System", plural: "Systems" },
  Account: { icon: Building2, label: "Customer", plural: "Customers" },
  Decision: { icon: Split, label: "Decision", plural: "Decisions" },
  Workaround: { icon: Wrench, label: "Workaround", plural: "Workarounds" },
};

export function TypeIcon({ type, className }: { type: ItemType; className?: string }) {
  const Icon = TYPE_META[type].icon;
  return <Icon aria-label={TYPE_META[type].label} className={cn("size-4 text-muted-foreground", className)} />;
}

/* ----------------------------------------------------------- source pill */

const SOURCE_META: Record<SourceKind, { icon: LucideIcon; name: string }> = {
  slack: { icon: Hash, name: "Slack" },
  doc: { icon: FileText, name: "Doc" },
  jira: { icon: SquareKanban, name: "Jira" },
  meeting: { icon: Video, name: "Meeting" },
  github: { icon: GitCommitHorizontal, name: "GitHub" },
  handover: { icon: MessagesSquare, name: "Handover answer" },
  support: { icon: LifeBuoy, name: "Support ticket" },
  crm: { icon: Contact, name: "HubSpot" },
  conversation: { icon: MessageSquareText, name: "Customer conversation" },
  roadmap: { icon: Map, name: "Roadmap" },
  promise: { icon: Handshake, name: "Promise" },
  other: { icon: FileText, name: "Source" },
};

/** The source-pill kind for a graph label (Ask path steps and cards only carry the label). */
export function kindForLabel(label?: string | null, hint?: string): SourceKind {
  if (hint && hint in SOURCE_META) return hint as SourceKind;
  switch (label) {
    case "Message":
      return "slack";
    case "Doc":
      return "doc";
    case "Ticket":
      return "jira";
    case "Meeting":
      return "meeting";
    case "Commit":
    case "PullRequest":
      return "github";
    case "Knowledge":
      return "handover";
    case "Conversation":
      return "conversation";
    case "Contact":
      return "crm";
    case "RoadmapItem":
      return "roadmap";
    case "Promise":
      return "promise";
    default:
      return "other";
  }
}

export function SourcePill({ source, compact, className }: { source: SourceRef; compact?: boolean; className?: string }) {
  const { openSource } = useApp();
  const meta = SOURCE_META[source.kind] ?? SOURCE_META.other;
  const Icon = meta.icon;
  const stale = source.freshness === "stale";
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        openSource(source);
      }}
      title={`${meta.name}: ${source.label}`}
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full border bg-card px-2 py-0.5 align-middle text-xs text-foreground/80 transition-colors transition-quiet hover:border-foreground/25 hover:text-foreground focus-visible:outline-2",
        className,
      )}
    >
      <Icon className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      <span className="sr-only">{meta.name}: </span>
      <span className={cn("truncate", compact ? "max-w-[10rem]" : "max-w-[16rem]")}>{source.label}</span>
      {stale ? <span className="ml-0.5 rounded-sm bg-warn-soft px-1 text-[10px] font-medium text-warn">stale</span> : null}
    </button>
  );
}

/* ----------------------------------------------------------- state badge */

export const STATE_META: Record<RiskState, { label: string; tone: "risk" | "warn" | "covered" | "neutral" | "brand" }> = {
  at_risk: { label: "At risk", tone: "risk" },
  assigned: { label: "Assigned", tone: "warn" },
  captured: { label: "Answered", tone: "brand" },
  verified: { label: "Verified", tone: "covered" },
  dismissed: { label: "Dismissed", tone: "neutral" },
  blocked: { label: "Blocked", tone: "risk" },
};

const TONE: Record<string, string> = {
  risk: "bg-risk-soft text-risk",
  warn: "bg-warn-soft text-warn",
  covered: "bg-covered-soft text-covered",
  brand: "bg-brand-soft text-brand",
  neutral: "bg-secondary text-muted-foreground",
};

const DOT: Record<string, string> = {
  risk: "bg-risk",
  warn: "bg-warn",
  covered: "bg-covered",
  brand: "bg-brand",
  neutral: "bg-muted-foreground/50",
};

export function StateBadge({ state, className }: { state: RiskState; className?: string }) {
  const m = STATE_META[state];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", TONE[m.tone], className)}>
      <span className={cn("size-1.5 rounded-full", DOT[m.tone])} aria-hidden />
      {m.label}
    </span>
  );
}

export function Dot({ tone }: { tone: keyof typeof DOT }) {
  return <span className={cn("inline-block size-1.5 rounded-full", DOT[tone])} aria-hidden />;
}

/* ---------------------------------------------------------- small pieces */

export function SectionTitle({ children, count, action }: { children: React.ReactNode; count?: number; action?: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-4">
      <h2 className="text-[18px] font-semibold tracking-[-0.09px]">
        {children}
        {count !== undefined ? <span className="ml-2 font-normal text-muted-foreground tabular">{count}</span> : null}
      </h2>
      {action}
    </div>
  );
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-mono text-[12.5px] tracking-tight", className)}>{children}</span>;
}

export function Card({ children, className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border bg-card", className)} {...rest}>
      {children}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed bg-card px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-muted-foreground">{body}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

/** One page-header pattern: small eyebrow, H1, at most one short subtitle line, optional actions. */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="text-[13px] font-medium text-muted-foreground">{eyebrow}</p> : null}
        <h1 className="mt-1 flex flex-wrap items-center gap-3 text-[30px] font-semibold leading-tight tracking-[-0.3px] md:text-[34px] md:tracking-[-0.4px]">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-2xl text-[15px] text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** Card header row: a 16px title, an optional count and an optional right-side link or action. */
export function CardTitle({ children, icon: Icon, action, className }: { children: React.ReactNode; icon?: LucideIcon; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-3", className)}>
      <h2 className="flex min-w-0 items-center gap-2 text-[16px] font-semibold">
        {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
        {children}
      </h2>
      {action}
    </div>
  );
}

/** Some server copy still carries internal scoring qualifiers. Strip them for display only. */
export function plain(text?: string | null): string {
  if (!text) return "";
  return text
    .replace(/\s*\((?:The [^()]*)?made-up demo data\.?\)/gi, "")
    .replace(/\s*\(demo score\)/gi, "")
    .replace(/\ba demo score\b/gi, "a score")
    .replace(/\bdemo score\b/gi, "score");
}

/** True for caveats or notes that only talk about the data being made up. */
export function isDemoNote(text?: string | null) {
  return !!text && /\b(demo score|demo data|made[- ]up|fictional|sample company)\b/i.test(text);
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-2xl bg-secondary", className)} />;
}

export function formatDay(iso?: string | null, opts?: Intl.DateTimeFormatOptions) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00+05:30` : iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Asia/Kolkata", ...opts });
}
