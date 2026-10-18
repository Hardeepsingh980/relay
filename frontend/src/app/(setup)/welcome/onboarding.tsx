"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Check, Loader2 } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { Avatar } from "@/components/relay/primitives";
import { RelayMark } from "@/components/shell/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConnectionsGrid, Labeled } from "@/components/workspace/connections";
import { InviteBox } from "@/components/workspace/team";
import { api, storePersona } from "@/lib/api";
import type { Persona } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = "you" | "workspace" | "connect" | "team" | "start";

const JOB_ROLES = ["Head of Customer Success", "Customer Success Manager", "Account Executive", "Engineering manager", "Founder", "Something else"];

const COMPANIES = [
  { id: "cheerio", name: "Cheerio", tagline: "WhatsApp marketing & commerce platform",
    body: "A sample WhatsApp marketing company with synthetic data: 45 people and 120 customers. Northwind Foods looks healthy in HubSpot but is at risk. Rahul leaves on Friday. A renewal call is on the calendar today.",
    modules: "Account Health · Handovers · Sales Assist" },
];

const CAST_ROLE: Record<Persona["persona"], string> = {
  head_cs: "Head of Customer Success · watches renewals",
  csm: "Customer success manager · runs the renewal call",
  manager: "Engineering manager · runs the handover",
  leaver: "Leaving · answers the open questions",
  joiner: "Joining · gets the answers",
};

// What each demo persona is for (the list itself comes from the workspace's company).
const PERSONA_COPY: Record<string, { wash: string; title: string; body: string }> = {
  head_cs: { wash: "bg-blush", title: "Watch every account", body: "See accounts that look healthy but are at risk, and people who are leaving. Investigate Northwind in one click." },
  csm: { wash: "bg-powder", title: "Run today's renewal call", body: "Get a brief before the call, cards during it and the follow-up after." },
  manager: { wash: "bg-butter", title: "Run Rahul's handover", body: "See what only Rahul knows. Preview the departure and choose the next owners." },
  leaver: { wash: "bg-lavender", title: "Answer as Rahul", body: "Short questions about Rahul's own work, one at a time." },
  joiner: { wash: "bg-mint", title: "Start as the new joiner", body: "Day One shows the systems, five people to meet and Rahul's answers." },
};

export function Onboarding() {
  const { user, workspace, authLoading, refreshMe, session } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const fresh = params.get("new") === "1";
  const [step, setStep] = useState<Step | null>(null);
  const [name, setName] = useState("");
  const [jobRole, setJobRole] = useState<string | null>(null);
  const [wsName, setWsName] = useState("");
  const [persona, setPersona] = useState("");
  const [tenant, setTenant] = useState("cheerio");
  const personas = session?.personas ?? [];
  const chosen = persona || personas[0]?.id || "";
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/sign-in?next=/welcome");
      return;
    }
    if (step) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setName(user.name);
    setJobRole(user.jobRole ?? null);
    if (fresh) setStep("workspace");
    else if (!user.onboardedAt && !workspace) setStep("you");
    else if (!workspace) setStep("workspace");
    else if (!user.onboardedAt) setStep(workspace.role === "member" ? "start" : "you");
    else router.replace("/home");
  }, [authLoading, user, workspace, fresh, step, router]);

  useEffect(() => {
    const e = params.get("error");
    if (e) toast.error(e);
  }, [params]);

  const order: Step[] = useMemo(() => {
    if (fresh) return ["workspace", "connect", "team"];
    if (workspace?.role === "member" && user && !user.onboardedAt) return ["you", "start"];
    return ["you", "workspace", "connect", "team", "start"];
  }, [fresh, workspace?.role, user]);

  if (!user || !step) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <RelayMark className="size-8 animate-pulse" />
      </div>
    );
  }
  const idx = order.indexOf(step);
  const next = () => setStep(order[Math.min(idx + 1, order.length - 1)]);
  const back = idx > 0 ? () => setStep(order[idx - 1]) : undefined;

  const saveYou = async () => {
    setBusy(true);
    try {
      await api.patch("/api/me", { name, jobRole });
      refreshMe();
      if (workspace && order.includes("workspace") && !fresh) setStep(order[order.indexOf("workspace") + 1]);
      else next();
    } finally {
      setBusy(false);
    }
  };
  const createWs = async () => {
    setBusy(true);
    try {
      await api.post("/api/workspaces", { name: wsName, tenant });
      await refreshMe();
      next();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Relay did not create the workspace. Try again.");
    } finally {
      setBusy(false);
    }
  };
  const finish = async (target?: string) => {
    setBusy(true);
    try {
      if (chosen) await api.patch("/api/me", { defaultPersona: chosen });
      await api.post("/api/me/onboarded");
      if (chosen) storePersona(chosen);
      await refreshMe();
      router.replace(target ?? personas.find((p) => p.id === chosen)?.home ?? "/home");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh bg-background">
      <header className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 md:px-8">
        <Link href="/" className="flex items-center gap-2" aria-label="Relay home">
          <RelayMark />
          <span className="text-[17px] font-semibold tracking-[-0.2px]">Relay</span>
        </Link>
        <ol className="hidden items-center gap-2 md:flex" aria-label="Setup progress">
          {order.map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              <span
                className={cn(
                  "flex h-7 items-center gap-1.5 rounded-full px-3 text-[13px]",
                  i < idx ? "bg-covered-soft text-covered" : i === idx ? "bg-brand-soft font-medium text-primary" : "text-muted-foreground",
                )}
              >
                {i < idx ? <Check className="size-3.5" /> : <span className="tabular">{i + 1}</span>}
                {LABEL[s]}
              </span>
            </li>
          ))}
        </ol>
        <span className="text-[13px] text-muted-foreground md:hidden">
          Step {idx + 1} of {order.length}
        </span>
      </header>

      <main className="mx-auto grid max-w-[1200px] gap-10 px-5 pb-16 pt-6 md:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)] lg:pt-12">
        <section className="max-w-[620px]">
          {step === "you" ? (
            <Panel
              eyebrow="Welcome"
              title={`Hi ${(name || user.name).split(" ")[0]}, tell us about you.`}
              body="Answer two quick questions. Relay uses them to show you where to start."
            >
              <div className="space-y-5">
                <Labeled label="Your name">
                  <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
                </Labeled>
                <div>
                  <p className="mb-2 text-sm font-medium">What best describes you?</p>
                  <div className="flex flex-wrap gap-2">
                    {JOB_ROLES.map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => setJobRole(r)}
                        aria-pressed={jobRole === r}
                        className={cn(
                          "rounded-full border px-4 py-2 text-[14px] transition-colors",
                          jobRole === r ? "border-primary bg-brand-soft text-primary" : "bg-card hover:bg-secondary",
                        )}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <Footer onNext={saveYou} busy={busy} disabled={name.trim().length < 2} />
            </Panel>
          ) : null}

          {step === "workspace" ? (
            <Panel
              eyebrow="Your workspace"
              title="Name your workspace."
              body="This is where your team keeps its accounts, calls and handovers. You can change the name at any time."
            >
              <Labeled label="Workspace name">
                <Input
                  value={wsName}
                  onChange={(e) => setWsName(e.target.value)}
                  placeholder="For example, Cheerio Engineering"
                  autoFocus
                  onKeyDown={(e) => e.key === "Enter" && wsName.trim().length > 1 && createWs()}
                />
              </Labeled>
              <p className="mt-5 text-[14px] font-medium">Start with a sample company</p>
              <div className="mt-2 grid gap-3" role="radiogroup" aria-label="Sample company">
                {COMPANIES.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    role="radio"
                    aria-checked={tenant === c.id}
                    onClick={() => setTenant(c.id)}
                    className={cn(
                      "rounded-3xl border bg-card p-4 text-left transition-colors",
                      tenant === c.id ? "border-primary ring-2 ring-primary/15" : "hover:bg-secondary/60",
                    )}
                  >
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="text-[15px] font-medium">
                        {c.name} <span className="font-normal text-muted-foreground">· {c.tagline}</span>
                      </span>
                      {tenant === c.id ? <Check className="size-4 text-primary" /> : null}
                    </span>
                    <span className="mt-1 block text-[13.5px] leading-relaxed text-foreground/70">{c.body}</span>
                    <span className="mt-2 block text-[12px] text-muted-foreground">{c.modules}</span>
                  </button>
                ))}
              </div>
              <Footer onBack={fresh ? undefined : back} onNext={createWs} busy={busy} disabled={wsName.trim().length < 2} nextLabel={busy ? "Creating…" : "Create workspace"} />
            </Panel>
          ) : null}

          {step === "connect" ? (
            <Panel
              eyebrow="Connections"
              title="Connect your tools."
              body="Relay learns from the work your team already does. The sample company's sources are already connected. Connect Google or Jira so that approved actions also reach those tools."
            >
              <ConnectionsGrid compact />
              <Footer onBack={back} onNext={next} nextLabel="Continue" />
            </Panel>
          ) : null}

          {step === "team" ? (
            <Panel
              eyebrow="Teammates"
              title="Invite your teammates."
              body="Relay works best when customer success, sales and engineering share one workspace. Then the people who own accounts work with the people who know the systems."
            >
              <InviteBox />
              <Footer onBack={back} onNext={fresh ? () => finish("/home") : next} nextLabel={fresh ? "Open workspace" : "Continue"} secondary={fresh ? undefined : { label: "Skip for now", onClick: next }} />
            </Panel>
          ) : null}

          {step === "start" ? (
            <Panel
              eyebrow="Ready"
              title="Where do you want to start?"
              body={`The ${session?.demo.company ?? ""} demo has ${personas.length} people. To see the app as another person, use View as in the top bar.`}
            >
              <div className="grid gap-3">
                {personas.map((p) => {
                  const base = PERSONA_COPY[p.persona] ?? PERSONA_COPY.manager;
                  const leaver = personas.find((x) => x.persona === "leaver")?.name.split(" ")[0] ?? "the leaver";
                  const copy = { ...base, title: base.title.replace("Rahul", leaver), body: base.body.replaceAll("Rahul", leaver) };
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setPersona(p.id)}
                      aria-pressed={chosen === p.id}
                      className={cn(
                        "flex items-center gap-4 rounded-3xl border bg-card p-4 text-left transition-colors",
                        chosen === p.id ? "border-primary ring-2 ring-primary/15" : "hover:bg-secondary/60",
                      )}
                    >
                      <span className={cn("flex size-12 shrink-0 items-center justify-center rounded-2xl", copy.wash)}>
                        <Avatar name={p.name} size={32} className="bg-card" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">{copy.title}</span>
                        <span className="block text-[13.5px] text-muted-foreground">
                          {p.name} · {p.role}. {copy.body}
                        </span>
                      </span>
                      <span
                        className={cn(
                          "flex size-5 shrink-0 items-center justify-center rounded-full border",
                          chosen === p.id ? "border-primary bg-primary text-white" : "",
                        )}
                      >
                        {chosen === p.id ? <Check className="size-3" /> : null}
                      </span>
                    </button>
                  );
                })}
              </div>
              <Footer onBack={back} onNext={() => finish()} busy={busy} nextLabel="Open Relay" />
            </Panel>
          ) : null}
        </section>

        <aside className="hidden lg:block">
          <Illustration step={step} workspace={wsName || workspace?.name || "Your workspace"} />
        </aside>
      </main>
    </div>
  );
}

const LABEL: Record<Step, string> = { you: "About you", workspace: "Workspace", connect: "Connections", team: "Teammates", start: "Start" };

function Panel({ eyebrow, title, body, children }: { eyebrow: string; title: string; body: string; children: React.ReactNode }) {
  return (
    <div className="animate-in fade-in slide-in-from-bottom-1 duration-300">
      <p className="inline-flex rounded-full bg-brand-soft px-3 py-1 text-caption font-medium text-primary">{eyebrow}</p>
      <h1 className="mt-4 text-[36px] font-semibold leading-[1.1] tracking-[-0.4px] md:text-heading-lg">{title}</h1>
      <p className="mt-3 text-subheading text-muted-foreground">{body}</p>
      <div className="mt-8">{children}</div>
    </div>
  );
}

function Footer({
  onBack,
  onNext,
  busy,
  disabled,
  nextLabel = "Continue",
  secondary,
}: {
  onBack?: () => void;
  onNext: () => void;
  busy?: boolean;
  disabled?: boolean;
  nextLabel?: string;
  secondary?: { label: string; onClick: () => void };
}) {
  return (
    <div className="mt-10 flex items-center gap-2">
      {onBack ? (
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft /> Back
        </Button>
      ) : null}
      <div className="ml-auto flex items-center gap-2">
        {secondary ? (
          <Button variant="ghost" onClick={secondary.onClick}>
            {secondary.label}
          </Button>
        ) : null}
        <Button size="lg" onClick={onNext} disabled={busy || disabled}>
          {busy ? <Loader2 className="animate-spin" /> : null}
          {nextLabel}
          {!busy ? <ArrowRight /> : null}
        </Button>
      </div>
    </div>
  );
}

function Illustration({ step, workspace }: { step: Step; workspace: string }) {
  const { session } = useApp();
  const personas = session?.personas ?? [];
  const first = (role: Persona["persona"], fallback: string) =>
    personas.find((p) => p.persona === role)?.name.split(" ")[0] ?? fallback;
  const [leaverName, joinerName] = [first("leaver", "the leaver"), first("joiner", "the joiner")];
  const demoSteps = personas.some((p) => p.persona === "head_cs")
    ? ["Spot the hidden risk at Northwind", "Investigate: main contact left, one bug, usage down", `Preview ${leaverName}'s departure`,
       "Run the renewal call with Sales Assist", "Approve the follow-up", `${joinerName} starts Day One with ${leaverName}'s answers`]
    : ["See where knowledge is at risk", `Start ${leaverName}'s handover`, `Answer questions as ${leaverName}`,
       `Check the answers as ${first("manager", "the manager")}`, `${joinerName} starts Day One with the answers`,
       "Close the handover and see company risk go down"];
  const wash = { you: "bg-lavender", workspace: "bg-butter", connect: "bg-powder", team: "bg-blush", start: "bg-mint" }[step];
  return (
    <div className={cn("sticky top-8 rounded-3xl p-10 transition-colors duration-500", wash)}>
      <div className="rounded-[10px] bg-card p-5 shadow-panel">
        {step === "you" || step === "workspace" ? (
          <>
            <p className="text-caption text-muted-foreground">Workspace</p>
            <p className="mt-1 text-[20px] font-semibold tracking-[-0.1px]">{workspace}</p>
            <div className="mt-5 grid grid-cols-3 gap-2 text-center">
              {[
                ["4", "silent-risk accounts"],
                ["120", "customers"],
                ["23", "things only one person knows"],
              ].map(([v, l]) => (
                <div key={l} className="rounded-xl bg-background p-3">
                  <p className="text-[20px] font-semibold tabular">{v}</p>
                  <p className="text-[11px] leading-tight text-muted-foreground">{l}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 text-[13px] text-muted-foreground">Cheerio sample workspace · synthetic data</p>
          </>
        ) : null}
        {step === "connect" ? (
          <ul className="space-y-2.5">
            {["HubSpot · 120 accounts", "Support desk · 1,083 tickets", "Jira · 464 issues", "Slack · 3,000 messages", "Meetings · 57 transcripts", "Amplitude · 26 weeks of usage", "GitHub · 1,113 commits"].map((t) => (
              <li key={t} className="flex items-center gap-3 rounded-xl bg-background px-3 py-2.5 text-[14px]">
                <span className="size-2 rounded-full bg-covered" aria-hidden />
                {t}
              </li>
            ))}
          </ul>
        ) : null}
        {step === "team" ? (
          <div>
            <p className="text-[15px] font-medium">Everyone in the handover</p>
            <div className="mt-4 space-y-3">
              {personas.map((p) => [p.name, CAST_ROLE[p.persona]]).map(([n, r]) => (
                <div key={n} className="flex items-center gap-3">
                  <Avatar name={n} size={32} />
                  <div>
                    <p className="text-[14px] font-medium leading-tight">{n}</p>
                    <p className="text-xs text-muted-foreground">{r}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
        {step === "start" ? (
          <div>
            <p className="text-caption text-muted-foreground">Six things to try</p>
            <ol className="mt-3 space-y-2.5 text-[14px]">
              {demoSteps.map((t, i) => (
                <li key={t} className="flex items-center gap-3">
                  <span className="flex size-6 items-center justify-center rounded-full bg-brand-soft text-[12px] font-medium text-primary tabular">{i + 1}</span>
                  {t}
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </div>
    </div>
  );
}
