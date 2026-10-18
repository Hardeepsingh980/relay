"use client";

import { cn } from "@/lib/utils";
import type { Coverage } from "@/lib/types";

const SEGMENTS: { key: keyof Coverage["byState"]; label: string; cls: string }[] = [
  { key: "verified", label: "Verified", cls: "bg-covered" },
  { key: "captured", label: "Answered", cls: "bg-brand" },
  { key: "assigned", label: "Assigned", cls: "bg-warn" },
  { key: "at_risk", label: "At risk", cls: "bg-risk" },
  { key: "blocked", label: "Blocked", cls: "bg-risk/60" },
  { key: "dismissed", label: "Dismissed", cls: "bg-muted-foreground/30" },
];

export function CoverageBar({ coverage, className, legend = false }: { coverage: Coverage; className?: string; legend?: boolean }) {
  const total = Math.max(coverage.total, 1);
  return (
    <div className={className}>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-secondary"
        role="img"
        aria-label={SEGMENTS.filter((s) => coverage.byState[s.key]).map((s) => `${coverage.byState[s.key]} ${s.label.toLowerCase()}`).join(", ")}
      >
        {SEGMENTS.map((s) =>
          coverage.byState[s.key] ? (
            <span
              key={s.key}
              className={cn("h-full transition-[width] duration-300 ease-out", s.cls)}
              style={{ width: `${(coverage.byState[s.key] / total) * 100}%` }}
            />
          ) : null,
        )}
      </div>
      {legend ? (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground tabular">
          {SEGMENTS.filter((s) => coverage.byState[s.key]).map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1">
              <span className={cn("size-1.5 rounded-full", s.cls)} aria-hidden />
              {coverage.byState[s.key]} {s.label.toLowerCase()}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
