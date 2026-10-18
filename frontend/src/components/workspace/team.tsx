"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Check, Copy, Loader2, MailPlus, X } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { Avatar } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { PendingInvite, TeamMember } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SentInvite {
  id?: string;
  email: string;
  role?: string;
  status: string;
  link?: string;
}

export function InviteBox({ onSent }: { onSent?: (invites: SentInvite[]) => void }) {
  const [draft, setDraft] = useState("");
  const [emails, setEmails] = useState<string[]>([]);
  const [role, setRole] = useState("member");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<SentInvite[]>([]);

  const commit = (raw: string) => {
    const parts = raw.split(/[\s,;]+/).map((x) => x.trim().toLowerCase()).filter(Boolean);
    if (parts.length) setEmails((e) => Array.from(new Set([...e, ...parts])));
    setDraft("");
  };

  const send = async () => {
    const all = Array.from(new Set([...emails, ...draft.split(/[\s,;]+/).map((x) => x.trim().toLowerCase()).filter(Boolean)]));
    if (!all.length) return;
    setBusy(true);
    try {
      const r = await api.post<{ invites: SentInvite[] }>("/api/workspace/invites", { emails: all, role });
      setSent(r.invites);
      setEmails([]);
      setDraft("");
      onSent?.(r.invites);
      toast.success(`${r.invites.filter((i) => i.status === "pending").length} invite link${r.invites.length === 1 ? "" : "s"} ready`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create invites");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div
          className="flex min-h-10 flex-1 flex-wrap items-center gap-1.5 rounded-xl border border-input bg-card px-2 py-1.5 focus-within:border-ring"
          onClick={(e) => (e.currentTarget.querySelector("input") as HTMLInputElement | null)?.focus()}
        >
          {emails.map((e) => (
            <span key={e} className="inline-flex items-center gap-1 rounded-full bg-brand-soft py-0.5 pl-2.5 pr-1 text-[13px] text-primary">
              {e}
              <button type="button" aria-label={`Remove ${e}`} onClick={() => setEmails((x) => x.filter((y) => y !== e))} className="rounded-full p-0.5 hover:bg-white/60">
                <X className="size-3" />
              </button>
            </span>
          ))}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (["Enter", ",", " ", "Tab"].includes(e.key) && draft.trim()) {
                e.preventDefault();
                commit(draft);
              }
              if (e.key === "Backspace" && !draft && emails.length) setEmails((x) => x.slice(0, -1));
            }}
            onBlur={() => draft.trim() && commit(draft)}
            onPaste={(e) => {
              e.preventDefault();
              commit(e.clipboardData.getData("text"));
            }}
            placeholder={emails.length ? "" : "name@company.com, another@company.com"}
            aria-label="Teammate emails"
            className="min-w-[10rem] flex-1 bg-transparent px-1 text-[15px] outline-none placeholder:text-muted-foreground"
          />
        </div>
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger className="h-10 sm:w-32" aria-label="Role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="member">Member</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={send} disabled={busy || (!emails.length && !draft.trim())}>
          {busy ? <Loader2 className="animate-spin" /> : <MailPlus />} Invite
        </Button>
      </div>
      {sent.length ? (
        <div className="rounded-xl border bg-background p-4">
          <p className="text-sm font-medium">Share these links</p>
          <p className="mt-0.5 text-xs text-muted-foreground">Each link works once, for its email only.</p>
          <ul className="mt-3 space-y-2">
            {sent.map((s) => (
              <li key={s.email} className="flex items-center gap-2 rounded-xl border bg-card px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm">{s.email}</span>
                {s.link ? <CopyLink link={s.link} /> : <span className="text-xs text-muted-foreground">Already a member</span>}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function CopyLink({ link }: { link: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size="xs"
      variant="soft"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(link);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } catch {
          window.prompt("Copy this invite link", link);
        }
      }}
    >
      {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy link"}
    </Button>
  );
}

export function TeamList() {
  const { user, workspace } = useApp();
  const { data, mutate } = useSWR<{ members: TeamMember[]; invites: PendingInvite[] }>("/api/workspace/members");
  const admin = workspace?.role === "owner" || workspace?.role === "admin";
  if (!data) return <div className="h-40 animate-pulse rounded-2xl bg-secondary" />;
  return (
    <div className="space-y-6">
      <div className="overflow-hidden rounded-2xl border bg-card">
        {data.members.map((m) => (
          <div key={m.id} className="flex items-center gap-3 border-b px-5 py-3.5 last:border-0">
            <Avatar name={m.name} size={34} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">
                {m.name} {m.id === user?.id ? <span className="font-normal text-muted-foreground">(you)</span> : null}
              </p>
              <p className="truncate text-xs text-muted-foreground">{m.email}</p>
            </div>
            {admin && m.id !== user?.id && m.role !== "owner" ? (
              <Select
                value={m.role}
                onValueChange={async (v) => {
                  if (v === "remove") {
                    await api.request(`/api/workspace/members/${m.id}`, { method: "DELETE" });
                    toast(`Removed ${m.name}`);
                  } else {
                    await api.request(`/api/workspace/members/${m.id}`, { method: "PATCH", body: JSON.stringify({ role: v }) });
                  }
                  mutate();
                }}
              >
                <SelectTrigger size="sm" className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">Member</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="remove">Remove…</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <span className={cn("rounded-full px-2.5 py-0.5 text-xs capitalize", m.role === "owner" ? "bg-secondary font-medium text-foreground" : "bg-secondary text-muted-foreground")}>{m.role}</span>
            )}
          </div>
        ))}
      </div>
      {data.invites.length ? (
        <div>
          <p className="mb-2 text-sm font-medium">Pending invites</p>
          <div className="overflow-hidden rounded-2xl border bg-card">
            {data.invites.map((i) => (
              <div key={i.id} className="flex items-center gap-3 border-b px-5 py-3 last:border-0">
                <span className="flex size-8 items-center justify-center rounded-full border border-dashed text-muted-foreground">
                  <MailPlus className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{i.email}</p>
                  <p className="text-xs text-muted-foreground">
                    {i.role} · invited {i.invitedBy ? `by ${i.invitedBy}` : ""}
                  </p>
                </div>
                {admin ? (
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={async () => {
                      await api.request(`/api/workspace/invites/${i.id}`, { method: "DELETE" });
                      mutate();
                    }}
                  >
                    Withdraw
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
