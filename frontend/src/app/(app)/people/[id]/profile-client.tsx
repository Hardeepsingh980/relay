"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { Avatar, Card, Dot, Mono, SectionTitle, Skeleton, TYPE_META, TypeIcon, formatDay } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Handover, ItemType, Profile } from "@/lib/types";

const ORDER: ItemType[] = ["System", "Account", "Decision", "Workaround"];

// Default last day: the Friday after the data snapshot (Mon 19 Oct 2026).
const DEFAULT_LAST_DAY = "2026-10-23";

export function ProfileClient({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data } = useSWR<Profile>(`/api/people/${id}`);
  const { persona } = useApp();
  const [open, setOpen] = useState(false);
  if (!data) return <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8"><Skeleton className="h-40" /></div>;
  const p = data.person;
  const grouped = ORDER.map((t) => ({ t, items: data.knowsAbout.filter((k) => k.type === t) })).filter((g) => g.items.length);
  const canStart = persona === "p-priya" && p.status === "active" && !data.handover && p.id !== persona;
  return (
    <div className="mx-auto max-w-[960px] px-4 py-10 md:px-8">
      <Link href="/people" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> People
      </Link>
      <div className="mt-3 flex flex-wrap items-end gap-4">
        <Avatar name={p.name} size={56} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-muted-foreground">{p.team}</p>
          <h1 className="mt-1 text-[30px] font-semibold leading-tight tracking-[-0.3px] md:text-[34px] md:tracking-[-0.4px]">{p.name}</h1>
          <p className="mt-1 text-[15px] text-muted-foreground">
            {p.role}
            {data.manager ? ` · Reports to ${data.manager.name}` : ""}
          </p>
        </div>
        {data.handover ? (
          <Button asChild>
            <Link href={`/handovers/${data.handover.id}`}>
              Open handover <ArrowRight className="size-3.5" />
            </Link>
          </Button>
        ) : canStart ? (
          <Button onClick={() => setOpen(true)}>Start handover</Button>
        ) : null}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-[1fr_280px]">
        <section>
          <SectionTitle count={data.knowsAbout.length}>Knows about</SectionTitle>
          {grouped.length === 0 ? (
            <p className="text-muted-foreground">No strong knowledge links yet.</p>
          ) : (
            <div className="space-y-5">
              {grouped.map(({ t, items }) => (
                <div key={t}>
                  <p className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <TypeIcon type={t} className="size-3.5" /> {TYPE_META[t].plural}
                  </p>
                  <Card className="divide-y">
                    {items.map((k) => (
                      <div key={k.id} className="flex items-center gap-3 px-5 py-2.5">
                        {k.unique ? <Dot tone="neutral" /> : <span className="size-1.5" />}
                        <span className="min-w-0 flex-1 truncate">{t === "System" ? <Mono>{k.name}</Mono> : k.name}</span>
                        {k.unique ? <span className="text-xs text-muted-foreground">only {p.name.split(" ")[0]}</span> : null}
                        <span className="w-10 text-right text-xs text-muted-foreground tabular">{k.score.toFixed(2)}</span>
                      </div>
                    ))}
                  </Card>
                </div>
              ))}
            </div>
          )}
        </section>
        <aside className="space-y-4">
          <Card className="p-4" title="Strength comes from recent activity. Above 0.6 is strong. Another person above 0.4 counts as a backup.">
            <p className="text-[32px] font-semibold leading-none tabular">{data.uniqueCount}</p>
            <p className="mt-1 text-sm text-muted-foreground">things only {p.name.split(" ")[0]} knows</p>
          </Card>
          {p.status === "joining" ? (
            <Card className="p-4 text-sm">
              Joins {formatDay(p.startDate, { weekday: "short" })}.{" "}
              <Link href="/day-one" className="text-primary hover:underline">See Day One</Link>
            </Card>
          ) : null}
        </aside>
      </div>
      {canStart ? <StartHandover open={open} onOpenChange={setOpen} profile={data} /> : null}
    </div>
  );
}

function StartHandover({ open, onOpenChange, profile }: { open: boolean; onOpenChange: (o: boolean) => void; profile: Profile }) {
  const router = useRouter();
  const [lastDay, setLastDay] = useState(DEFAULT_LAST_DAY);
  const [joiner, setJoiner] = useState<string>(profile.incomingJoiners[0]?.id ?? "none");
  const [busy, setBusy] = useState(false);
  const first = profile.person.name.split(" ")[0];
  const start = async () => {
    setBusy(true);
    try {
      const h = await api.post<Handover>("/api/handovers", {
        leaverId: profile.person.id,
        lastDay,
        joinerId: joiner === "none" ? null : joiner,
      });
      router.push(`/handovers/${h.handover.id}?analyze=1`);
    } catch (e) {
      toast.error("Could not start the handover", { description: e instanceof Error ? e.message : undefined });
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Start {first}&apos;s handover</DialogTitle>
          <DialogDescription>Find what only {first} knows and pick next owners.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Last day</span>
            <Input type="date" value={lastDay} min="2026-10-19" onChange={(e) => setLastDay(e.target.value)} />
          </label>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Who takes over the work</span>
            <Select value={joiner} onValueChange={setJoiner}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {profile.incomingJoiners.map((j) => (
                  <SelectItem key={j.id} value={j.id}>
                    {j.name} · joins {formatDay(j.startDate)}
                  </SelectItem>
                ))}
                <SelectItem value="none">No joiner yet</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">They see the answers on Day One.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={start} disabled={busy || !lastDay}>
            {busy ? "Starting…" : "Start and analyze"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
