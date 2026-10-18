"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { toast } from "sonner";
import {
  Building2,
  CalendarClock,
  Check,
  ChevronDown,
  House,
  LogOut,
  MessageCircleQuestion,
  Network,
  Plug,
  Plus,
  Repeat2,
  RotateCcw,
  Search,
  Settings,
  GitBranch,
  Info,
  Sunrise,
  Users,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import { useApp } from "@/components/app-provider";
import { Avatar } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import type { Journey } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Relay mark: two lanes and the hand-off between them. */
export function RelayMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("size-7", className)} aria-hidden>
      <rect x="1.5" y="1.5" width="21" height="21" rx="7" className="fill-foreground" />
      <path d="M6.5 15.5c3.2 0 4-7 7.4-7h3.6" fill="none" strokeWidth="2.4" strokeLinecap="round" className="stroke-background" />
      <circle cx="6.6" cy="15.5" r="1.9" className="fill-background" />
      <circle cx="17.4" cy="8.5" r="1.9" fill="#008ae8" />
    </svg>
  );
}


interface NavItem {
  href?: string;
  label: string;
  icon: LucideIcon;
  onClick?: () => void;
  match?: (p: string) => boolean;
}

function useNavItems(): { main: NavItem[]; more: NavItem[] } {
  const { persona, session } = useApp();
  const health = session?.modules.accountHealth ?? false;
  const main: NavItem[] = [
    { href: "/home", label: "Home", icon: House, match: (p) => p === "/home" },
    { href: "/graph", label: "Knowledge graph", icon: Network, match: (p) => p.startsWith("/graph") },
    ...(health ? [{ href: "/accounts", label: "Accounts", icon: Building2, match: (p: string) => p.startsWith("/accounts") }] : []),
    { href: "/people", label: "People", icon: Users, match: (p) => p.startsWith("/people") },
    ...(health ? [{ href: "/meetings", label: "Meetings", icon: CalendarClock, match: (p: string) => p.startsWith("/meetings") }] : []),
    { href: "/ask", label: "Ask", icon: Search, match: (p) => p.startsWith("/ask") },
    { href: "/settings/connections", label: "Settings", icon: Settings, match: (p) => p.startsWith("/settings") },
  ];
  const more: NavItem[] = [
    { href: "/handovers", label: "Handovers", icon: Repeat2, match: (p) => p.startsWith("/handovers") },
    { href: "/repos", label: "Repo knowledge", icon: GitBranch, match: (p) => p.startsWith("/repos") },
  ];
  if (persona === "p-rahul") more.push({ href: "/interview", label: "My handover", icon: MessageCircleQuestion, match: (p) => p.startsWith("/interview") });
  if (persona === "p-aisha") more.push({ href: "/day-one", label: "Day One", icon: Sunrise, match: (p) => p.startsWith("/day-one") });
  return { main, more };
}

function WorkspaceMenu() {
  const { workspace, workspaces, session } = useApp();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  if (!workspace) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="flex w-full min-w-0 items-center gap-2 rounded-xl px-2 py-1.5 text-left hover:bg-secondary">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-mint text-[12px] font-semibold">{workspace.name[0]?.toUpperCase()}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-medium leading-tight">{workspace.name}</span>
            <span className="block truncate text-[11px] text-muted-foreground leading-tight">{session?.demo.company ?? workspace.company} sample data</span>
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel className="font-normal">
          <p className="text-[11px] text-muted-foreground">Workspaces</p>
        </DropdownMenuLabel>
        {workspaces.map((w) => (
          <DropdownMenuItem
            key={w.id}
            onSelect={async () => {
              if (w.id === workspace.id) return;
              await api.post(`/api/workspaces/${w.id}/switch`);
              await mutate(() => true);
              router.push("/home");
            }}
          >
            <span className="flex size-6 items-center justify-center rounded-lg bg-lavender text-[11px] font-semibold">{w.name[0]?.toUpperCase()}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate">{w.name}</span>
              {w.company ? <span className="block truncate text-[11px] text-muted-foreground">{w.company}</span> : null}
            </span>
            {w.id === workspace.id ? <Check className="size-4 text-primary" /> : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings/connections">
            <Plug className="size-4" /> Connections
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings/team">
            <UsersRound className="size-4" /> Teammates
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings/workspace">
            <Settings className="size-4" /> Workspace settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/welcome?new=1">
            <Plus className="size-4" /> New workspace
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const ROLE_LABEL: Record<string, string> = {
  head_cs: "Head of CS",
  csm: "CSM",
  manager: "Manager",
  leaver: "Leaving",
  joiner: "Joining",
};

const ROLE_BLURB: Record<string, string> = {
  head_cs: "Head of Customer Success · watches renewals",
  csm: "Customer Success Manager · runs today's renewal call",
  manager: "Engineering manager · runs the handover",
  leaver: "Leaving Friday · answers a few questions",
  joiner: "Starts today · takes over the work",
};


function PersonaMenu() {
  const { session, persona, setPersona, workspace, user, signOut } = useApp();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!session) return <div className="h-9 w-40" />;
  const current = session.personas.find((p) => p.id === persona) ?? session.personas[0];
  const admin = workspace?.role === "owner" || workspace?.role === "admin";

  const reset = async () => {
    setBusy(true);
    try {
      await api.post("/api/demo/reset", { confirm: true });
      await mutate(() => true);
      toast.success("Workspace reset", { description: "Accounts, calls, handovers, answers and actions are back to the start." });
      router.push("/home");
    } catch (e) {
      toast.error("Reset failed", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={user?.sandbox ? `Signed in as ${current.name}` : `View as: ${current.name}`}
            className="flex items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3 text-[13.5px] hover:bg-secondary"
          >
            <Avatar name={current.name} size={28} />
            <span className="hidden text-left leading-tight sm:block">
              <span className="block font-medium">{current.name.split(" ")[0]}</span>
              <span className="block text-[11px] text-muted-foreground">{ROLE_LABEL[current.persona]}</span>
            </span>
            <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-80">
          <DropdownMenuLabel className="font-normal">
            <p className="text-[11px] text-muted-foreground">{user?.sandbox ? "Signed in as" : "View as"}</p>
            {user?.sandbox ? <p className="mt-0.5 text-[14px] font-medium text-foreground">{current.name}</p> : null}
          </DropdownMenuLabel>
          {user?.sandbox ? (
            <DropdownMenuLabel className="pt-0 font-normal">
              <p className="text-[11px] text-muted-foreground">Switch to</p>
            </DropdownMenuLabel>
          ) : null}
          {session.personas
            .filter((p) => !user?.sandbox || p.id !== current.id)
            .map((p) => (
              <DropdownMenuItem
                key={p.id}
                onSelect={() => {
                  setPersona(p.id);
                  router.push(p.home);
                }}
                className="py-2"
              >
                <Avatar name={p.name} size={30} />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{p.name}</span>
                  <span className="block text-xs text-muted-foreground">{ROLE_BLURB[p.persona]}</span>
                </span>
                {p.id === current.id ? <Check className="size-4 text-primary" /> : null}
              </DropdownMenuItem>
            ))}
          {admin ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setConfirm(true)}>
                <RotateCcw className="size-4" /> Reset workspace…
              </DropdownMenuItem>
            </>
          ) : null}
          {user?.sandbox ? (
            <DropdownMenuItem onSelect={() => signOut()}>
              <LogOut className="size-4" /> Sign out
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Reset this workspace?</DialogTitle>
            <DialogDescription>
              The {session.demo.company} graph goes back to how it started. Investigations, calls, handovers, answers and
              actions are cleared.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={reset} disabled={busy}>
              {busy ? "Resetting…" : "Reset"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function AccountMenu() {
  const { user, signOut } = useApp();
  if (!user || user.sandbox) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label="Account" className="rounded-full focus-visible:outline-2">
          {user.avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatarUrl} alt="" className="size-9 rounded-full" referrerPolicy="no-referrer" />
          ) : (
            <Avatar name={user.name} size={36} className="bg-powder" />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium">{user.name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings/profile">
            <Settings className="size-4" /> Profile & preferences
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/">
            <Info className="size-4" /> About Relay
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => signOut()}>
          <LogOut className="size-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ProgressRing({ done, total, className }: { done: number; total: number; className?: string }) {
  const c = 2 * Math.PI * 8;
  return (
    <svg viewBox="0 0 20 20" className={cn("size-4 -rotate-90", className)} aria-hidden>
      <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeDasharray={`${(done / Math.max(total, 1)) * c} ${c}`} />
    </svg>
  );
}

function JourneyPill() {
  const { data } = useSWR<Journey>("/api/journey", { refreshInterval: 15_000 });
  if (!data || data.dismissed || data.done === data.total) return null;
  return (
    <Link
      href="/home#journey"
      className="hidden items-center gap-2 rounded-full bg-brand-soft px-3 py-1.5 text-[13px] font-medium text-primary hover:bg-[color-mix(in_oklab,var(--brand-soft),var(--primary)_10%)] xl:flex"
    >
      <ProgressRing done={data.done} total={data.total} />
      Getting started · {data.done}/{data.total}
    </Link>
  );
}

function NavLink({ it, pathname }: { it: NavItem; pathname: string }) {
  const active = it.match?.(pathname) ?? false;
  return (
    <Link
      href={it.href!}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-[14.5px] font-medium transition-colors transition-quiet",
        active ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
      )}
    >
      <it.icon className={cn("size-[18px]", active ? "text-foreground" : "text-muted-foreground")} aria-hidden />
      {it.label}
    </Link>
  );
}

function Sidebar() {
  const pathname = usePathname();
  const { main, more } = useNavItems();
  const { session } = useApp();
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[232px] flex-col border-r bg-card md:flex">
      <Link href="/home" aria-label="Relay home" className="flex h-16 shrink-0 items-center gap-2 px-5">
        <RelayMark />
        <span className="text-[17px] font-semibold tracking-[-0.2px]">Relay</span>
      </Link>
      <div className="px-3">
        <WorkspaceMenu />
      </div>
      <nav aria-label="Main" className="mt-4 flex flex-col gap-0.5 px-3">
        {main.map((it) => (
          <NavLink key={it.label} it={it} pathname={pathname} />
        ))}
      </nav>
      <div className="mt-6 px-5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Knowledge</div>
      <nav aria-label="More" className="mt-1.5 flex flex-col gap-0.5 px-3">
        {more.map((it) => (
          <NavLink key={it.label} it={it} pathname={pathname} />
        ))}
      </nav>
      <div className="mt-auto px-5 pb-5 text-[11px] leading-snug text-muted-foreground">
        {session ? <p>{session.demo.company} · today {new Date(session.demo.now).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" })}</p> : null}
      </div>
    </aside>
  );
}

function TopBar() {
  const { openAsk } = useApp();
  return (
    <header className="fixed inset-x-0 top-0 z-30 border-b bg-card/95 backdrop-blur md:left-[232px]">
      <div className="flex h-16 items-center gap-2 px-4 md:px-6">
        <Link href="/home" aria-label="Relay home" className="shrink-0 md:hidden">
          <RelayMark />
        </Link>
        <button
          type="button"
          onClick={() => openAsk()}
          className="flex h-9 min-w-0 max-w-md flex-1 items-center gap-2 rounded-full border bg-background pl-3 pr-2 text-[13.5px] text-muted-foreground hover:text-foreground"
        >
          <Search className="size-4 shrink-0" aria-hidden />
          <span className="truncate">Ask anything about accounts, people or systems…</span>
          <kbd className="ml-auto hidden rounded-full bg-secondary px-1.5 py-0.5 text-[10px] sm:inline">⌘K</kbd>
        </button>
        <div className="ml-auto flex items-center gap-2">
          <JourneyPill />
          <PersonaMenu />
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}

function MobileNav() {
  const pathname = usePathname();
  const items = useNavItems().main.filter((i) => i.label !== "Settings");
  return (
    <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 flex border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
      {items.map((it) => {
        const active = it.match?.(pathname) ?? false;
        return (
          <Link
            key={it.label}
            href={it.href!}
            aria-current={active ? "page" : undefined}
            className={cn("flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]", active ? "text-primary" : "text-muted-foreground")}
          >
            <it.icon className="size-5" aria-hidden />
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Sidebar />
      <TopBar />
      <main className="min-h-dvh pb-20 pt-16 md:pb-0 md:pl-[232px]">{children}</main>
      <MobileNav />
    </>
  );
}
