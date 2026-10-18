"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { ArrowRight, Check, ChevronDown, X } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { ProgressRing } from "@/components/shell/shell";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Journey, JourneyStep } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Compact "Getting started" checklist: progress, the next step, and the full list on demand. */
export function JourneyCard() {
  const { data, mutate } = useSWR<Journey>("/api/journey", { refreshInterval: 10_000 });
  const { setPersona, persona, openAsk, session } = useApp();
  const [expanded, setExpanded] = useState(false);
  const nameOf = (id: string) => session?.personas.find((p) => p.id === id)?.name.split(" ")[0] ?? id;
  const router = useRouter();
  if (!data || data.dismissed) return null;

  const go = (s: JourneyStep) => {
    if (s.persona && s.persona !== persona) setPersona(s.persona);
    if (s.ask) {
      router.push(s.href);
      setTimeout(() => openAsk(s.ask), 350);
      return;
    }
    router.push(s.href);
  };
  const groups = Array.from(new Set(data.steps.map((s) => s.group)));
  const next = data.steps.find((s) => s.id === data.next);
  const complete = data.done === data.total;
  const switching = next?.persona && next.persona !== persona ? nameOf(next.persona) : null;

  return (
    <section id="journey" aria-label="Getting started" className="scroll-mt-24 rounded-2xl border bg-card">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <ProgressRing done={data.done} total={data.total} className={cn("size-6 shrink-0", complete ? "text-covered" : "text-primary")} />
        <div className="min-w-[200px] flex-1">
          <p className="text-[14px] font-semibold leading-tight">
            Getting started
            <span className="ml-2 font-normal text-muted-foreground tabular">
              {data.done} of {data.total}
            </span>
          </p>
          <p className="truncate text-[13px] text-muted-foreground">
            {complete ? "All steps done." : next ? `Next: ${next.label}${switching ? ` · as ${switching}` : ""}` : "Pick any step below."}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {next ? (
            <Button size="sm" onClick={() => go(next)} title={switching ? `Switches you to ${switching}` : undefined}>
              Continue <ArrowRight />
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-expanded={expanded}
            aria-controls="journey-steps"
            aria-label={expanded ? "Collapse steps" : "Show all steps"}
            onClick={() => setExpanded((v) => !v)}
          >
            <ChevronDown className={cn("transition-transform", expanded && "rotate-180")} />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Hide checklist"
            onClick={async () => {
              await api.post("/api/journey/journey-dismissed");
              mutate();
            }}
          >
            <X />
          </Button>
        </div>
      </div>

      {expanded ? (
        <div id="journey-steps" className={cn("grid gap-x-6 gap-y-4 border-t px-4 py-4", groups.length > 4 ? "md:grid-cols-3 xl:grid-cols-5" : "md:grid-cols-4")}>
          {groups.map((g) => (
            <div key={g}>
              <p className="text-caption font-medium text-muted-foreground">{g}</p>
              <ul className="mt-2 space-y-0.5">
                {data.steps
                  .filter((s) => s.group === g)
                  .map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        onClick={() => go(s)}
                        className={cn(
                          "flex w-full items-start gap-2 rounded-lg px-1.5 py-1.5 text-left text-[13.5px] transition-colors hover:bg-secondary",
                          s.id === data.next && "bg-secondary",
                        )}
                      >
                        <span
                          className={cn(
                            "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
                            s.done ? "border-covered bg-covered text-white" : s.id === data.next ? "border-primary" : "border-ash",
                          )}
                        >
                          {s.done ? <Check className="size-2.5" strokeWidth={3} /> : null}
                        </span>
                        <span className={cn("leading-snug", s.done && "text-muted-foreground")}>
                          {s.label}
                          {s.persona && !s.done ? <span className="block text-[11px] text-muted-foreground">as {nameOf(s.persona)}</span> : null}
                        </span>
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
