"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Avatar } from "@/components/relay/primitives";
import { authApi, storePersona, type TeamMember, type TeamPreview } from "@/lib/api";

let cached: Promise<{ company: string; members: TeamMember[]; preview: TeamPreview }> | null = null;

/** The sample team and live numbers from its graph (one request, shared by the picker and the side panel). */
export function useTeam() {
  const [data, setData] = useState<{ company: string; members: TeamMember[]; preview: TeamPreview } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    cached ??= authApi.team();
    cached.then(setData).catch((e) => {
      cached = null;
      setError(e instanceof Error ? e.message : "Relay could not load the team.");
    });
  }, []);
  return { data, error };
}

/** One click signs you in as a teammate, inside this browser's own copy of the workspace. */
export function TeamPicker({ next }: { next?: string | null }) {
  const { data, error } = useTeam();
  const [busy, setBusy] = useState<string | null>(null);

  const go = async (m: TeamMember) => {
    setBusy(m.id);
    try {
      await authApi.teamSignIn(m.id);
      storePersona(m.id);
      window.location.assign(next && next !== "/home" ? next : m.home);
    } catch (e) {
      toast.error("Could not sign in", { description: e instanceof Error ? e.message : undefined });
      setBusy(null);
    }
  };

  if (error) return <p className="rounded-xl bg-risk-soft px-4 py-3 text-sm text-risk">{error}</p>;
  return (
    <ul className="divide-y overflow-hidden rounded-2xl border bg-card" aria-label="Sign in as">
      {(data?.members ?? Array.from({ length: 5 }, () => null)).map((m, i) =>
        m ? (
          <li key={m.id}>
            <button
              type="button"
              onClick={() => go(m)}
              disabled={!!busy}
              className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-secondary/60 disabled:opacity-60"
            >
              <Avatar name={m.name} size={36} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="font-medium">{m.name}</span>
                  <span className="truncate text-xs text-muted-foreground">{m.role}</span>
                </span>
                <span className="block truncate text-[13px] text-muted-foreground">{m.task}</span>
              </span>
              {busy === m.id ? (
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              ) : (
                <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
              )}
            </button>
          </li>
        ) : (
          <li key={i} className="flex items-center gap-3 px-4 py-3">
            <span className="size-9 animate-pulse rounded-full bg-secondary" />
            <span className="h-4 w-48 animate-pulse rounded bg-secondary" />
          </li>
        ),
      )}
    </ul>
  );
}

const fmt = (n: number) => n.toLocaleString("en-IN");

/** Live numbers from the sample workspace's graph (no hardcoded figures). */
export function LivePreview({ className }: { className?: string }) {
  const { data } = useTeam();
  const p = data?.preview;
  return (
    <div className={className}>
      <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-covered opacity-60" />
          <span className="relative inline-flex size-2 rounded-full bg-covered" />
        </span>
        Live from the {data?.company ?? "Cheerio"} graph{p ? ` · ${p.ms} ms` : ""}
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-2xl border bg-border">
        {[
          ["Nodes", p?.nodes],
          ["Relationships", p?.relationships],
          ["Support tickets", p?.counts.Ticket],
          ["Customers", p?.counts.Account],
          ["Slack messages", p?.counts.Message],
          ["People", p?.counts.Person],
        ].map(([label, n]) => (
          <div key={label as string} className="bg-card px-4 py-3">
            <dt className="text-[12px] text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 text-[20px] font-semibold tabular">{typeof n === "number" ? fmt(n) : "…"}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 rounded-2xl border bg-card">
        <p className="border-b px-4 py-2.5 text-[12.5px] font-medium text-muted-foreground">Healthy in HubSpot, at risk in the graph</p>
        <ul className="divide-y">
          {(p?.silent ?? []).map((a) => (
            <li key={a.name} className="flex items-center gap-3 px-4 py-2.5 text-[14px]">
              <span className="flex-1 truncate font-medium">{a.name}</span>
              <span className="text-xs text-muted-foreground tabular">HubSpot {a.crm}</span>
              <span className="w-12 text-right font-semibold text-risk tabular">{a.risk}%</span>
            </li>
          ))}
          {!p ? <li className="px-4 py-6 text-center text-sm text-muted-foreground">Loading…</li> : null}
        </ul>
      </div>
    </div>
  );
}
