"use client";

import { ArrowDownRight, ArrowUpRight, EyeOff } from "lucide-react";

import { cn } from "@/lib/utils";
import { crmTone, riskTone, type Factor } from "@/lib/relay";

const TONE_TEXT = { risk: "text-risk", warn: "text-warn", covered: "text-covered" } as const;
const TONE_BG = { risk: "bg-risk-soft text-risk", warn: "bg-warn-soft text-warn", covered: "bg-covered-soft text-covered" } as const;
const TONE_BAR = { risk: "bg-risk", warn: "bg-warn", covered: "bg-covered" } as const;

/** Relay's graph risk, with the change since the last scan. */
export function RiskNumber({ risk, previous, size = "md", className }: { risk: number; previous?: number | null; size?: "sm" | "md" | "lg"; className?: string }) {
  const tone = riskTone(risk);
  const delta = previous !== null && previous !== undefined ? risk - previous : 0;
  return (
    <span className={cn("inline-flex items-baseline gap-1.5", className)}>
      <span
        className={cn(
          "font-semibold tabular leading-none",
          TONE_TEXT[tone],
          size === "lg" ? "text-[44px] tracking-[-0.4px]" : size === "md" ? "text-[22px]" : "text-[15px]",
        )}
      >
        {risk}%
      </span>
      {delta ? (
        <span className={cn("inline-flex items-center text-[12px] font-medium tabular", delta > 0 ? "text-risk" : "text-covered")}>
          {delta > 0 ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownRight className="size-3.5" aria-hidden />}
          {Math.abs(delta)}
          <span className="sr-only"> points since the last scan</span>
        </span>
      ) : null}
    </span>
  );
}

export function CrmScore({ crm, className }: { crm: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium tabular", TONE_BG[crmTone(crm)], className)}>
      HubSpot {crm}
    </span>
  );
}

export function SilentBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full bg-risk-soft px-2 py-0.5 text-[11.5px] font-medium text-risk", className)}
      title="Looks healthy in HubSpot (70+) but is at risk in Relay (60%+)"
    >
      <EyeOff className="size-3" aria-hidden /> Silent risk
    </span>
  );
}

/** CRM health vs Relay risk on one line: the gap is the story. */
export function HealthVsRisk({ crm, risk, previous }: { crm: number; risk: number; previous?: number | null }) {
  const tone = riskTone(risk);
  return (
    <div className="space-y-2.5">
      <div>
        <div className="flex items-baseline justify-between text-[12px] text-muted-foreground">
          <span>HubSpot health</span>
          <span className="font-medium text-foreground tabular">{crm}</span>
        </div>
        <div className="mt-1 h-1.5 rounded-full bg-secondary">
          <div className={cn("h-1.5 rounded-full", TONE_BAR[crmTone(crm)])} style={{ width: `${crm}%` }} />
        </div>
      </div>
      <div>
        <div className="flex items-baseline justify-between text-[12px] text-muted-foreground">
          <span>Relay risk</span>
          <RiskNumber risk={risk} previous={previous} size="sm" />
        </div>
        <div className="mt-1 h-1.5 rounded-full bg-secondary">
          <div className={cn("h-1.5 rounded-full transition-all duration-700", TONE_BAR[tone])} style={{ width: `${risk}%` }} />
        </div>
      </div>
    </div>
  );
}

export function FactorList({ factors, base }: { factors: Factor[]; base?: number }) {
  const sorted = [...factors].sort((a, b) => b.points - a.points);
  return (
    <ul className="divide-y">
      {sorted.map((f) => (
        <li key={f.key} className="flex items-start gap-3 py-2.5">
          <span
            className={cn(
              "mt-0.5 w-11 shrink-0 rounded-full py-0.5 text-center text-[12px] font-semibold tabular",
              f.points > 0 ? "bg-risk-soft text-risk" : "bg-covered-soft text-covered",
            )}
          >
            {f.points > 0 ? "+" : ""}
            {f.points}
          </span>
          <span className="min-w-0">
            <span className="block text-[14px] font-medium leading-snug">{f.label}</span>
            <span className="block text-[12.5px] text-muted-foreground">{f.detail}</span>
          </span>
        </li>
      ))}
      {base !== undefined ? (
        <li className="flex items-center gap-3 py-2.5 text-[12.5px] text-muted-foreground">
          <span className="w-11 shrink-0 rounded-full bg-secondary py-0.5 text-center font-semibold tabular">+{base}</span>
          Starting points for every account
        </li>
      ) : null}
    </ul>
  );
}

/** Weekly series as a tiny bar chart; missing weeks stay as gaps (never interpolated). */
export function Sparkbars({ series, className, highlightFrom = 22 }: { series: { week: string; value: number }[]; className?: string; highlightFrom?: number }) {
  if (!series.length) return null;
  const max = Math.max(...series.map((s) => s.value), 1);
  const byWeek = new Map(series.map((s) => [s.week, s.value]));
  const weeks = series.map((s) => s.week);
  return (
    <div className={cn("flex h-12 items-end gap-[2px]", className)} role="img" aria-label="Weekly usage">
      {weeks.map((w, i) => {
        const v = byWeek.get(w) ?? 0;
        return (
          <span
            key={w}
            title={`${w}: ${v}`}
            className={cn("flex-1 rounded-[2px]", i >= highlightFrom ? "bg-foreground/70" : "bg-foreground/20")}
            style={{ height: `${Math.max(4, (v / max) * 100)}%` }}
          />
        );
      })}
    </div>
  );
}

/** Where an action lands. Internal mode values stay as the API sends them; only the label changes. */
export function modeLabel(mode: string) {
  return mode === "live" ? "Live" : mode === "draft" ? "Draft" : "Saved in Relay";
}

export function ModeBadge({ mode }: { mode: string }) {
  const live = mode === "live";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium",
        live ? "bg-covered-soft text-covered" : mode === "draft" ? "bg-brand-soft text-brand" : "bg-secondary text-muted-foreground",
      )}
      title={live ? "Runs in the connected tool" : mode === "draft" ? "Saved as a draft. Nothing is sent." : "Kept in Relay. No outside tool changes."}
    >
      {modeLabel(mode)}
    </span>
  );
}

/** Display copy for action statuses (internal values unchanged). */
export const ACTION_STATUS: Record<string, { label: string; cls: string }> = {
  proposed: { label: "Needs approval", cls: "bg-secondary text-muted-foreground" },
  approved: { label: "Approved", cls: "bg-brand-soft text-brand" },
  running: { label: "Running…", cls: "bg-brand-soft text-brand" },
  succeeded: { label: "Done", cls: "bg-covered-soft text-covered" },
  drafted: { label: "Draft", cls: "bg-brand-soft text-brand" },
  simulated: { label: "Saved in Relay", cls: "bg-secondary text-muted-foreground" },
  failed: { label: "Failed", cls: "bg-risk-soft text-risk" },
  needs_attention: { label: "Needs attention", cls: "bg-warn-soft text-warn" },
};

export function ActionStatusChip({ status }: { status: string }) {
  const m = ACTION_STATUS[status] ?? { label: status, cls: "bg-secondary text-muted-foreground" };
  return <span className={cn("inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium", m.cls)}>{m.label}</span>;
}
