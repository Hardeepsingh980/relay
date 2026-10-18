"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { toast } from "sonner";
import {
  AlertOctagon,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bug,
  CircleCheck,
  Code2,
  Copy,
  Handshake,
  LoaderCircle,
  Map as MapIcon,
  MessageSquareQuote,
  Keyboard,
  Mic,
  MicOff,
  Radio,
  Send,
  ShieldCheck,
  Swords,
  UserRound,
  Volume2,
  VolumeX,
} from "lucide-react";

import { ActionStatusChip, CrmScore, ModeBadge, RiskNumber, SilentBadge } from "@/components/health/bits";
import { Avatar, Card, PageHeader, Skeleton, formatDay } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { dayIST, mmss, timeIST, type Brief, type CallCard, type CallResult, type CallSession, type MeetingRecord, type PlanAction, type Segment, type StreamEvent } from "@/lib/relay";
import { useStream } from "@/lib/use-stream";
import { cn } from "@/lib/utils";

export function MeetingClient({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, mutate } = useSWR<MeetingRecord>(`/api/meetings/${id}`);
  const scheduled = data?.meeting.status === "scheduled";
  const { data: brief } = useSWR<Brief>(scheduled || data?.call ? `/api/meetings/${id}/brief` : null);
  const [callId, setCallId] = useState<string | null>(null);
  const activeCall = callId ?? data?.call?.id ?? null;

  if (!data) return <Loading />;
  if (activeCall) return <LiveCall id={activeCall} brief={brief ?? null} meetingId={id} onRefresh={() => mutate()} />;
  if (scheduled) return brief ? <BriefView brief={brief} onStarted={setCallId} /> : <Loading />;
  return <PastMeeting rec={data} />;
}

/* ------------------------------------------------------------------ brief */

function BriefView({ brief, onStarted }: { brief: Brief; onStarted: (id: string) => void }) {
  const b = brief;
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const start = async (live = false) => {
    setBusy(true);
    try {
      const s = await api.post<CallSession>(`/api/meetings/${b.meeting.id}/call`, { speed, live });
      onStarted(s.id);
    } catch (e) {
      toast.error("The call did not start", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  };
  const external = b.attendees.filter((a) => !a.internal);
  const internal = b.attendees.filter((a) => a.internal);
  return (
    <div className="mx-auto max-w-[1240px] px-4 py-8 md:px-8">
      <Link href="/meetings" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Meetings
      </Link>
      <div className="mt-3 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <PageHeader
            eyebrow={`Call brief · ${dayIST(b.meeting.start)} ${timeIST(b.meeting.start)}–${timeIST(b.meeting.end)} IST${
              b.meeting.startsIn > 0 ? ` · starts in ${b.meeting.startsIn >= 60 ? `${Math.floor(b.meeting.startsIn / 60)} h ${b.meeting.startsIn % 60} min` : `${b.meeting.startsIn} min`}` : ""
            }`}
            title={b.meeting.title}
          />
          <div className="mt-4 flex flex-wrap gap-4">
            {external.map((a) => (
              <span key={a.id} className="inline-flex items-center gap-2">
                <Avatar name={a.name} size={30} />
                <span className="leading-tight">
                  <span className="block text-[14px] font-medium">{a.name}</span>
                  <span className="block text-[12px] text-muted-foreground">
                    {a.title}
                    {a.replaced ? ` · replaced ${a.replaced}` : ""}
                  </span>
                </span>
              </span>
            ))}
            <span className="inline-flex items-center gap-1 text-[12.5px] text-muted-foreground">
              with {internal.map((a) => a.name.split(" ")[0]).join(", ")}
            </span>
          </div>
        </div>
        <Card className="self-start p-5">
          <p className="text-[15px] font-semibold">Join with Sales Assist</p>
          <p className="mt-0.5 text-[13px] text-muted-foreground" title="A meeting bot transcribes the call. Everyone hears that it is recorded.">
            Live cards appear in a panel only you see.
          </p>
          <div className="mt-3 flex items-center gap-1 text-[12.5px]" role="radiogroup" aria-label="Replay speed">
            {[1, 2, 4].map((x) => (
              <button
                key={x}
                role="radio"
                aria-checked={speed === x}
                onClick={() => setSpeed(x)}
                className={cn("rounded-full px-2.5 py-1 font-medium", speed === x ? "bg-foreground text-background" : "bg-secondary text-muted-foreground")}
              >
                {x}×
              </button>
            ))}
            <span className="ml-1 text-muted-foreground">speed</span>
          </div>
          <Button className="mt-4 w-full" size="lg" onClick={() => start()} disabled={busy || !b.meeting.recording}>
            <Radio className="size-4" /> {busy ? "Connecting…" : "Start the call"}
          </Button>
          <p className="mt-2 text-center text-[12px] text-muted-foreground">Plays the recorded call, with audio.</p>
          <Button className="mt-3 w-full" variant="outline" onClick={() => start(true)} disabled={busy}>
            <Keyboard className="size-4" /> Start a live call
          </Button>
          <p className="mt-2 text-center text-[12px] text-muted-foreground">Type or speak each line yourself.</p>
        </Card>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-[16px] font-semibold">
                <Link href={`/accounts/${b.account.id}`} className="hover:underline">
                  {b.account.name}
                </Link>
              </h2>
              <div className="flex items-center gap-2">
                {b.account.silent ? <SilentBadge /> : null}
                <CrmScore crm={b.account.crm} />
                <RiskNumber risk={b.account.risk} size="sm" />
              </div>
            </div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              {b.account.arrLabel} ARR · {b.account.plan} · renews {formatDay(b.account.renewalDate)} ({b.account.renewalInDays} days, {b.account.stage}) · wallet {b.account.wallet}
            </p>
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {b.account.factors.filter((f) => f.points > 0).map((f) => (
                <li key={f.key} className="rounded-full border px-2 py-0.5 text-[12px]">
                  {f.label} <span className="font-medium text-risk tabular">+{f.points}</span>
                </li>
              ))}
            </ul>
          </Card>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <Card className="p-5">
              <h2 className="text-[16px] font-semibold">Goals for this call</h2>
              <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-[14px]">
                {b.goals.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ol>
            </Card>
            <Card className="p-5">
              <h2 className="text-[16px] font-semibold">Questions to ask</h2>
              <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-[14px]">
                {b.questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ol>
            </Card>
          </div>
          {b.dont.length ? (
            <Card className="border-l-[3px] border-l-warn p-5">
              <h2 className="flex items-center gap-2 text-[16px] font-semibold">
                <AlertOctagon className="size-4 text-warn" aria-hidden /> Do not say
              </h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[14px]">
                {b.dont.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </Card>
          ) : null}
          <Card className="p-5">
            <h2 className="text-[16px] font-semibold">Promises made to them</h2>
            <ul className="mt-3 space-y-2">
              {b.promises.map((p) => (
                <li key={p.id} className={cn("rounded-xl border p-3 text-[14px]", p.atRisk && "border-warn/40")}>
                  <p className="font-medium">{p.text}</p>
                  <p className="text-[12.5px] text-muted-foreground">
                    {p.madeBy} · {p.meeting} · due {p.due} · <b className={p.atRisk ? "text-warn" : ""}>{p.atRisk ? p.why : p.status}</b>
                  </p>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5">
            <h2 className="text-[16px] font-semibold">History</h2>
            {b.history.map((h) => (
              <div key={h.id} className="mt-3">
                <p className="text-[14px] font-medium">
                  {h.title} <span className="font-normal text-muted-foreground">· {h.date}</span>
                </p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[13px] text-muted-foreground">
                  {h.summary.map((x) => (
                    <li key={x}>{x.replace(/\*\*/g, "")}</li>
                  ))}
                </ul>
              </div>
            ))}
            {b.signals.length ? (
              <div className="mt-4 space-y-2">
                {b.signals.map((s, i) => (
                  <blockquote key={i} className="rounded-xl border-l-2 border-foreground/20 bg-background px-3 py-2 text-[13px]">
                    “{s.quote}” <span className="text-muted-foreground">· {s.speaker}, {s.date}</span>
                  </blockquote>
                ))}
              </div>
            ) : null}
          </Card>
        </div>
        <aside className="space-y-6">
          <Card className="p-5">
            <h2 className="text-[16px] font-semibold">Open issues</h2>
            {b.openIssues.map((i) => (
              <div key={i.bugId} className="mt-3 rounded-xl border p-3 text-[13px]">
                <p>
                  <span className="font-mono text-[12px]">{i.bugId}</span> · {i.title}
                </p>
                <p className="mt-0.5 text-muted-foreground">
                  {i.status} · {i.priority} · owner {i.owner} · {i.tickets} tickets
                </p>
                {i.workaround ? <p className="mt-1 text-[12.5px]">Workaround: {i.workaround}</p> : null}
              </div>
            ))}
          </Card>
          <Card className="p-5">
            <h2 className="text-[16px] font-semibold">Roadmap they care about</h2>
            {b.roadmap.map((r) => (
              <div key={r.id} className="mt-3 text-[13px]">
                <p className="font-medium">{r.title}</p>
                <p className="text-muted-foreground">
                  {r.status} · {r.eta} {r.originally && r.originally !== r.eta ? `(was ${r.originally})` : ""}
                </p>
              </div>
            ))}
          </Card>
          <Card className="p-5">
            <h2 className="text-[16px] font-semibold">Experts on your team</h2>
            <ul className="mt-3 space-y-2.5">
              {b.experts.map((e) => (
                <li key={`${e.id}-${e.about}`} className="flex items-center gap-2.5 text-[13px]">
                  <Avatar name={e.name} size={28} ring={e.leaving ? "risk" : undefined} />
                  <span className="min-w-0">
                    <span className="block font-medium leading-tight">{e.name}</span>
                    <span className="block text-muted-foreground leading-tight">{e.why}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <p className="px-1 text-[12px] text-muted-foreground" title={`Sources: ${b.sources.join(", ")}`}>
            Updated {timeIST(b.generatedAt)} IST
          </p>
        </aside>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ live call */

interface CallState {
  status: CallSession["status"];
  duration: number;
  speed: number;
  live: boolean;
  recording: string | null;
  speakers: Record<string, string>;
  transcript: Segment[];
  cards: CallCard[];
  result: CallResult | null;
  ended: boolean;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function reduceCall(s: CallState, ev: StreamEvent): CallState {
  const p = ev.payload as any;
  switch (ev.type) {
    case "call.started":
      return { ...s, status: "live", duration: p.duration, speed: p.speed, live: Boolean(p.live), recording: p.recording ?? null, speakers: p.speakers ?? {} };
    case "transcript.segment":
      return { ...s, transcript: [...s.transcript, p.segment] };
    case "card.added":
      return { ...s, cards: [...s.cards, p.card] };
    case "card.updated":
      return { ...s, cards: s.cards.map((c) => (c.id === p.card.id ? p.card : c)) };
    case "call.ended":
      return { ...s, status: "ended", ended: true };
    case "call.summarised":
      return { ...s, status: "summarised", result: p.result };
    case "call.actions":
      return s.result ? { ...s, result: { ...s.result, actions: p.actions } } : s;
    case "call.failed":
      return { ...s, status: "failed" };
    default:
      return s;
  }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

const CALL0: CallState = { status: "ready", duration: 0, speed: 1, live: false, recording: null, speakers: {}, transcript: [], cards: [], result: null, ended: false };

function LiveCall({ id, brief, meetingId, onRefresh }: { id: string; brief: Brief | null; meetingId: string; onRefresh: () => void }) {
  const [s] = useStream<CallState>(`/api/calls/${id}/events`, reduceCall, CALL0);
  const { mutate } = useSWRConfig();
  const scroller = useRef<HTMLDivElement>(null);
  const [ending, setEnding] = useState(false);
  const elapsed = s.transcript.length ? s.transcript[s.transcript.length - 1].t : 0;
  const live = s.status === "live" || s.status === "ready";

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [s.transcript.length]);

  // Play each recorded line's audio as it arrives (the "Start the call" click unlocks audio in the browser).
  const [sound, setSound] = useState(true);
  const played = useRef(0);
  useEffect(() => {
    const fresh = s.transcript.slice(played.current);
    played.current = s.transcript.length;
    if (!sound || !s.recording || s.speed !== 1) return;
    const last = [...fresh].reverse().find((seg) => typeof seg.r === "number");
    if (last && fresh.length <= 2) {
      const audio = new Audio(`/calls/${s.recording}/${last.r}.mp3`);
      audio.play().catch(() => setSound(false));
    }
  }, [s.transcript, s.recording, s.speed, sound]);
  useEffect(() => {
    if (s.status === "summarised") {
      onRefresh();
      mutate((k) => typeof k === "string" && (k.startsWith("/api/accounts") || k.startsWith("/api/home")));
    }
  }, [s.status, onRefresh, mutate]);

  const end = async () => {
    setEnding(true);
    try {
      await api.post(`/api/calls/${id}/end`);
    } finally {
      setEnding(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-6 md:px-6">
      <Link href="/meetings" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Meetings
      </Link>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12.5px] font-medium", live ? "bg-risk-soft text-risk" : "bg-secondary text-muted-foreground")}>
          {live ? <span className="size-2 animate-pulse rounded-full bg-risk" aria-hidden /> : <CircleCheck className="size-3.5" />}
          {live ? "Recording" : s.status === "summarised" ? "Call ended · summary ready" : "Call ended"}
        </span>
        <h1 className="min-w-0 flex-1 truncate text-[22px] font-semibold tracking-[-0.2px]">{brief?.meeting.title ?? "Customer call"}</h1>
        <span className="font-mono text-[13px] tabular text-muted-foreground">
          {mmss(elapsed)} / {mmss(s.duration)} {s.speed !== 1 ? `· ${s.speed}×` : ""}
        </span>
        {s.recording ? (
          <Button variant="ghost" size="sm" onClick={() => setSound((v) => !v)} aria-label={sound ? "Mute call audio" : "Play call audio"}>
            {sound ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
          </Button>
        ) : null}
        {live ? (
          <Button variant="outline" size="sm" onClick={end} disabled={ending}>
            {ending ? "Ending…" : "End call"}
          </Button>
        ) : null}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Card className="flex h-[min(68vh,640px)] flex-col overflow-hidden">
            <div className="flex items-center gap-2 border-b px-5 py-3 text-[13px] text-muted-foreground">
              <Mic className="size-4" aria-hidden /> Live transcript
            </div>
            <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-5 py-4" aria-live="polite">
              {s.transcript.map((seg) => (
                <div key={seg.i} className="flex gap-3">
                  <Avatar name={seg.speaker_name} size={28} />
                  <div className="min-w-0">
                    <p className="text-[12px] text-muted-foreground">
                      <span className="font-medium text-foreground">{seg.speaker_name}</span> {seg.internal ? "· Cheerio" : ""} · {mmss(seg.t)}
                    </p>
                    <p className="text-[14.5px] leading-relaxed">{seg.text}</p>
                  </div>
                </div>
              ))}
              {live && !s.transcript.length ? (
                <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  {s.live ? "Type or speak the first line below." : "Waiting for the first words…"}
                </p>
              ) : null}
            </div>
            {live && s.status === "live" ? <Composer callId={id} speakers={s.speakers} /> : null}
          </Card>
          {s.status === "ended" ? (
            <Card className="flex items-center gap-2 p-5 text-[14px] text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" /> Saving the summary and follow-ups…
            </Card>
          ) : null}
          {s.result ? <Summary result={s.result} callId={id} meetingId={meetingId} /> : null}
        </div>
        <LivePanel cards={s.cards} callId={id} live={live} />
      </div>
    </div>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start: () => void; stop: () => void;
  onresult: ((e: any) => void) | null; onend: (() => void) | null; onerror: ((e: any) => void) | null };

/** Add a line to the call: typed, or spoken through the browser's speech recognition. */
function Composer({ callId, speakers }: { callId: string; speakers: Record<string, string> }) {
  const [who, setWho] = useState<"customer" | "rep">("customer");
  const [text, setText] = useState("");
  const [interim, setInterim] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const whoRef = useRef(who);
  useEffect(() => {
    whoRef.current = who;
  }, [who]);
  const canSpeak = typeof window !== "undefined" && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const send = async (line: string, speaker = whoRef.current) => {
    const t = line.trim();
    if (!t) return;
    setBusy(true);
    try {
      await api.post(`/api/calls/${callId}/say`, { text: t, who: speaker });
      setText("");
    } catch (e) {
      toast.error("Relay could not add the line", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    if (listening) {
      rec.current?.stop();
      return;
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const r: Recognition = new SR();
    r.lang = "en-IN";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e: any) => {
      let partial = "";
      for (let k = e.resultIndex; k < e.results.length; k++) {
        const res = e.results[k];
        if (res.isFinal) void send(res[0].transcript);
        else partial += res[0].transcript;
      }
      setInterim(partial);
    };
    r.onend = () => {
      setListening(false);
      setInterim("");
    };
    r.onerror = (e: any) => toast.error("Microphone stopped", { description: e?.error });
    rec.current = r;
    r.start();
    setListening(true);
  };
  useEffect(() => () => rec.current?.stop(), []);

  return (
    <form
      className="border-t p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void send(text);
      }}
    >
      <div className="mb-2 flex items-center gap-1 text-[12.5px]" role="radiogroup" aria-label="Who is speaking">
        <span className="mr-1 text-muted-foreground">Speaking:</span>
        {(["customer", "rep"] as const).map((k) =>
          speakers[k] ? (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={who === k}
              onClick={() => setWho(k)}
              className={cn("rounded-full px-2.5 py-1 font-medium", who === k ? "bg-foreground text-background" : "bg-secondary text-muted-foreground")}
            >
              {speakers[k]} {k === "customer" ? "(customer)" : "(you)"}
            </button>
          ) : null,
        )}
      </div>
      <div className="flex items-center gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={interim || (who === "customer" ? "For example: Is SSO coming in December?" : "For example: I'll send you the fix date by Friday.")}
          aria-label="Say a line"
          className="h-10 min-w-0 flex-1 rounded-xl border bg-background px-3 text-[14px] outline-none focus:border-primary"
        />
        {canSpeak ? (
          <Button type="button" variant={listening ? "default" : "outline"} size="icon" onClick={toggleMic} aria-label={listening ? "Stop listening" : "Speak"}>
            {listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
          </Button>
        ) : null}
        <Button type="submit" disabled={busy || !text.trim()}>
          <Send className="size-4" /> Say
        </Button>
      </div>
    </form>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

const CARD_ICON: Record<CallCard["kind"], React.ComponentType<{ className?: string }>> = {
  answer: BookOpen,
  roadmap: MapIcon,
  bug: Bug,
  objection: Swords,
  expert: UserRound,
  promise: Handshake,
  risk: AlertOctagon,
  consent: ShieldCheck,
};

function LivePanel({ cards, callId, live }: { cards: CallCard[]; callId: string; live: boolean }) {
  const ordered = useMemo(() => [...cards].reverse(), [cards]);
  return (
    <aside className="lg:sticky lg:top-20 lg:self-start">
      <div className="w-full rounded-2xl border bg-card lg:w-[360px]">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="text-[14px] font-semibold">Sales Assist</p>
          <span className="text-[12px] text-muted-foreground tabular">Only you · {cards.length} cards</span>
        </div>
        <ul className="max-h-[min(78vh,760px)] space-y-2.5 overflow-y-auto p-3" aria-live="polite" aria-label="Live cards">
          {!cards.length ? (
            <li className="px-2 py-6 text-center text-[13px] text-muted-foreground">{live ? "Listening for topics…" : "No cards on this call."}</li>
          ) : null}
          {ordered.map((c) => (
            <LiveCard key={c.id} c={c} callId={callId} />
          ))}
        </ul>
      </div>
    </aside>
  );
}

function LiveCard({ c, callId }: { c: CallCard; callId: string }) {
  const [showCypher, setShowCypher] = useState(false);
  const [busy, setBusy] = useState(false);
  const Icon = CARD_ICON[c.kind];
  const tone = c.tone === "red" ? "border-l-[3px] border-l-risk" : c.tone === "amber" ? "border-l-[3px] border-l-warn" : "";
  const copy = async () => {
    await navigator.clipboard.writeText(c.copy ?? `${c.title}\n${c.body}`).catch(() => null);
    toast.success("Copied");
  };
  const ping = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ status: string; message: string }>(`/api/calls/${callId}/cards/${c.id}/ping`);
      toast.success(r.status === "simulated" ? "Saved in Relay" : "Slack message sent", { description: r.message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className={cn("animate-in fade-in slide-in-from-top-2 rounded-xl border bg-card p-3 duration-300", tone)}>
      <div className="flex items-start gap-2">
        <Icon className={cn("mt-0.5 size-4 shrink-0", c.tone === "red" ? "text-risk" : c.tone === "amber" ? "text-warn" : "text-muted-foreground")} />
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold leading-snug">{c.title}</p>
          <p className="mt-1 text-[13px] leading-snug text-foreground/80">{c.body}</p>
          {c.path?.hops.length ? (
            <ol aria-label="How you are connected to this person" className="mt-2 flex flex-wrap items-center gap-1 text-[11px]">
              {c.path.hops.map((h, i) => (
                <li key={`${h.id}-${i}`} className="flex items-center gap-1">
                  {i ? <span className="text-muted-foreground" aria-hidden>→</span> : null}
                  <span className="max-w-[10rem] truncate rounded-full border bg-card px-2 py-0.5" title={h.name}>
                    {h.label === "Ticket" ? h.id : h.name.split(" ")[0]}
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        {c.source ? (
          <span className="inline-flex max-w-[12rem] items-center gap-1 rounded-full border bg-card px-2 py-0.5">
            <MessageSquareQuote className="size-3" aria-hidden />
            <span className="truncate">{c.source.label}</span>
          </span>
        ) : null}
        <span className="tabular">
          {mmss(c.t)} · {c.latencyMs} ms
        </span>
        <span className="ml-auto flex items-center gap-1">
          {c.queries.length ? (
            <button type="button" onClick={() => setShowCypher((v) => !v)} className="rounded-full p-1 hover:bg-secondary" aria-label="Show Cypher" title="Show the graph query (Cypher)">
              <Code2 className="size-3.5" />
            </button>
          ) : null}
          <button type="button" onClick={copy} className="rounded-full p-1 hover:bg-secondary" aria-label="Copy card">
            <Copy className="size-3.5" />
          </button>
        </span>
      </div>
      {c.action?.kind === "ping" ? (
        c.pinged ? (
          <p className="mt-2 flex items-start gap-2 rounded-xl bg-background px-2.5 py-1.5 text-[12px]">
            <ModeBadge mode={c.pinged.status === "succeeded" ? "live" : "simulated"} /> <span className="min-w-0">{c.pinged.message}</span>
          </p>
        ) : (
          <Button size="sm" variant="outline" className="mt-2 w-full" onClick={ping} disabled={busy}>
            <Send className="size-3.5" /> Message {c.action.to.split(" ")[0]} in Slack
          </Button>
        )
      ) : null}
      {showCypher ? (
        <div className="mt-2 space-y-1.5">
          {c.queries.map((q, i) => (
            <pre key={i} className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-background p-2 font-mono text-[10px] leading-snug">
              {q.cypher}
              {"\n"}
              <span className="text-muted-foreground">
                {q.rows} rows · {q.ms} ms
              </span>
            </pre>
          ))}
        </div>
      ) : null}
    </li>
  );
}

/* ------------------------------------------------------------------ after the call */

function Summary({ result, callId, meetingId }: { result: CallResult; callId: string; meetingId: string }) {
  const [busy, setBusy] = useState(false);
  const pending = result.actions.filter((a) => a.status === "proposed" || a.status === "failed");
  const approve = async (ids: string[]) => {
    setBusy(true);
    try {
      await api.post(`/api/calls/${callId}/approve`, { actionIds: ids });
      toast.success(`Approved ${ids.length} action${ids.length > 1 ? "s" : ""}`);
    } catch (e) {
      toast.error("Approval failed", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  };
  const h = result.health;
  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[13px] font-medium text-muted-foreground">After the call · saved in {result.ms} ms</p>
            <h2 className="mt-1 text-[20px] font-semibold">Summary</h2>
          </div>
          <div className="rounded-xl border px-4 py-2 text-right">
            <p className="text-[11.5px] text-muted-foreground">Account risk</p>
            <p className="flex items-center gap-1.5 text-[18px] font-semibold tabular">
              {h.before ?? "—"}% <ArrowRight className="size-4 text-muted-foreground" /> {h.after}%
            </p>
            <p className="text-[11px] text-muted-foreground">{h.hint}</p>
          </div>
        </div>
        <Notes text={result.notes} />
        {result.superseded.length ? (
          <p className="mt-4 rounded-xl border px-3 py-2 text-[13px]">
            <span className="font-medium text-covered">Promise replaced:</span> “{result.superseded.map((x) => x.text).join("”, “")}”
          </p>
        ) : null}
        <p className="mt-4">
          <Link href={`/meetings/${meetingId}`} className="text-[13px] text-primary hover:underline">
            Meeting record
          </Link>
        </p>
      </Card>
      <Card className="p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-semibold">Follow-ups</h2>
            <p className="text-[13px] text-muted-foreground">The customer email is saved as a draft, not sent.</p>
          </div>
          {pending.length ? (
            <Button onClick={() => approve(pending.map((a) => a.id))} disabled={busy}>
              <ShieldCheck className="size-4" /> Approve all {pending.length}
            </Button>
          ) : null}
        </div>
        <ul className="mt-4 space-y-3">
          {result.actions.map((a) => (
            <FollowAction key={a.id} a={a} onApprove={() => approve([a.id])} busy={busy} />
          ))}
        </ul>
      </Card>
    </div>
  );
}

function FollowAction({ a, onApprove, busy }: { a: PlanAction; onApprove: () => void; busy: boolean }) {
  const p = a.payload as Record<string, string>;
  const preview = a.type === "email.draft" ? `To: ${(a.payload.to as string[]).join(", ")}\nSubject: ${p.subject}\n\n${p.body}` : a.type === "crm.note" ? p.note : `${p.title}\n${p.description ?? ""}`;
  return (
    <li className="rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 font-medium">{a.title}</p>
        {a.customerFacing ? <span className="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn">Goes to customer</span> : null}
        {a.status === "proposed" || a.status === "failed" ? (
          <>
            <ModeBadge mode={a.destination.mode} />
            <Button size="sm" variant="outline" onClick={onApprove} disabled={busy}>
              Approve
            </Button>
          </>
        ) : (
          <ActionStatusChip status={a.status} />
        )}
      </div>
      <details className="mt-2 text-[12.5px]">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Preview</summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-background p-3 font-sans text-[13px] leading-relaxed">{preview}</pre>
      </details>
      {a.result ? (
        <p className="mt-2 text-[12.5px] text-muted-foreground">
          {a.result.message}
          {a.approvedBy ? ` · approved by ${a.approvedBy}` : ""}
        </p>
      ) : null}
    </li>
  );
}

function Notes({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="mt-4 space-y-1 text-[14px] leading-relaxed">
      {lines.map((l, i) => {
        if (!l.trim()) return <div key={i} className="h-2" />;
        if (l === "Overview" || l === "Action Items") return <p key={i} className="pt-1 text-[12.5px] font-semibold uppercase tracking-wide text-muted-foreground">{l}</p>;
        const bold = l.match(/^\*\*(.+)\*\*$/);
        if (bold) return <p key={i} className="pt-1 font-semibold">{bold[1]}</p>;
        const bullet = l.match(/^- (?:\*\*(.+?):\*\* )?(.*)$/);
        if (bullet)
          return (
            <p key={i} className="pl-4 -indent-3">
              • {bullet[1] ? <b>{bullet[1]}: </b> : null}
              {bullet[2]}
            </p>
          );
        return <p key={i}>{l}</p>;
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ past meeting */

function PastMeeting({ rec }: { rec: MeetingRecord }) {
  const m = rec.meeting;
  return (
    <div className="mx-auto max-w-[960px] px-4 py-8 md:px-8">
      <Link href="/meetings" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Meetings
      </Link>
      <PageHeader
        className="mt-3"
        eyebrow={
          <>
            {formatDay(m.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })} ·{" "}
            {rec.accountId ? (
              <Link href={`/accounts/${rec.accountId}`} className="hover:underline">
                {rec.account}
              </Link>
            ) : (
              "Internal"
            )}
          </>
        }
        title={m.title}
      />
      {m.notes ? (
        <Card className="mt-6 p-5">
          <Notes text={m.notes} />
        </Card>
      ) : null}
      {rec.promises.length ? (
        <Card className="mt-6 p-5">
          <h2 className="text-[16px] font-semibold">Promises from this meeting</h2>
          <ul className="mt-3 space-y-2 text-[14px]">
            {rec.promises.map((p) => (
              <li key={p.id} className="rounded-xl border p-3">
                <p className={cn("font-medium", p.status === "superseded" && "line-through text-muted-foreground")}>{p.text}</p>
                <p className="text-[12.5px] text-muted-foreground">
                  due {p.due} · {p.status}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {m.transcript.length ? (
        <Card className="mt-6 p-5">
          <h2 className="text-[16px] font-semibold">Transcript</h2>
          <div className="mt-3 space-y-3">
            {m.transcript.map((x, i) => (
              <p key={i} className="text-[14px] leading-relaxed">
                <span className="font-medium">{x.speakerName ?? "Speaker"}</span>
                {x.t !== undefined ? <span className="text-[12px] text-muted-foreground"> · {mmss(x.t)}</span> : null}
                <br />
                {x.text}
              </p>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function Loading() {
  return (
    <div className="mx-auto max-w-[1240px] px-4 py-10 md:px-8">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="mt-3 h-10 w-96" />
      <Skeleton className="mt-8 h-[420px]" />
    </div>
  );
}
