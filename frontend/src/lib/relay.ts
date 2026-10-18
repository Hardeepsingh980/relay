// Shapes for Relay's Account Health, Sales Assist and "under the hood" APIs.

export interface Factor {
  key: string;
  label: string;
  points: number;
  detail: string;
}

export interface RadarRow {
  id: string;
  name: string;
  arr: number;
  arrLabel: string;
  plan: string;
  renewalDate: string;
  renewalInDays: number;
  crm: number;
  risk: number;
  previousRisk: number | null;
  hint: string;
  silent: boolean;
  band: "critical" | "high" | "watch" | "healthy";
  industry: string;
  planted: string;
  stage: string;
  csm: string | null;
  csmId: string | null;
  nextMeeting: string | null;
}

export interface Radar {
  asOf: string;
  accounts: RadarRow[];
  silent: { count: number; arr: number; arrLabel: string };
  note: string;
}

export interface CostlyBug {
  bugId: string;
  title: string;
  priority: string;
  status: string;
  jiraStatus: string | null;
  owner: string | null;
  ownerId: string | null;
  accounts: number;
  arr: number;
  tickets: number;
  ageDays: number;
  underPrioritised: boolean;
  hit: { id: string; name: string; arr: number }[];
}

export interface PromiseRow {
  id: string;
  text: string;
  due: string;
  status: "open" | "kept" | "superseded" | "broken";
  atRisk: boolean;
  why: string | null;
  madeBy: string | null;
  madeById: string | null;
  meeting: string | null;
  meetingId: string | null;
  quote: string | null;
  dependsOn: { id: string; title?: string; status?: string; eta?: string; kind: string } | null;
}

export interface OwnerPerson {
  id: string;
  name: string;
  role: string;
  leaving: boolean;
  lastDay: string | null;
  relations: string[];
  knows: number | null;
}

export interface IssueCluster {
  bugId: string;
  bugTitle: string;
  bugStatus: string;
  jiraStatus: string | null;
  bugPriority: string;
  bugKeyword: string;
  bugAgeDays: number;
  bugWorkaround: string | null;
  feature: string | null;
  owner: string | null;
  ownerId: string | null;
  open: boolean;
  tickets: { id: string; title: string; createdAt: string; status: string; confidence: number; method: string; raisedBy: string }[];
}

export interface UsageMetric {
  key: string;
  metric: string;
  baseline: number;
  current: number;
  declinePct: number;
  series?: { week: string; value: number }[];
  missingWeeks: number[];
}

export interface TimelineEvent {
  date: string;
  kind: string;
  nodeId: string;
  label: string;
  signals?: string[];
}

export interface ActionLogRow {
  id: string;
  title: string;
  type: string;
  status: string;
  mode: string;
  approvedBy: string | null;
  approvedAt: string | null;
  at: string | null;
  message: string | null;
  account: string | null;
  accountId: string | null;
}

export interface AccountDetail {
  account: {
    id: string;
    name: string;
    arr: number;
    arrLabel: string;
    renewalDate: string;
    renewalInDays: number;
    crmHealthScore: number;
    detectiveRisk: number;
    industry: string;
    plan: string;
    seats: number;
    renewalStage: string;
    walletBalance: number;
    walletLabel: string;
    country: string;
    csm: { id: string; name: string } | null;
    ae: { id: string; name: string } | null;
    features: string[];
  };
  risk: { risk: number; factors: Factor[]; hint: string; crm: number; silent: boolean; asOf: string; queries: Record<string, string> };
  contacts: {
    id: string;
    name: string;
    title: string;
    role: string;
    champion: boolean;
    active: boolean;
    since: string;
    left: string | null;
    email: string;
    emailStatus: string;
    replaced: string | null;
  }[];
  meetings: { id: string; title: string; date: string; status: string; recording: string | null; promises: number }[];
  promises: PromiseRow[];
  owners: { people: OwnerPerson[]; leaving: OwnerPerson[] };
  issues: IssueCluster[];
  usage: { weeklyActiveUsers: UsageMetric | null; featureDeclines: UsageMetric[]; window: string };
  timeline: TimelineEvent[];
  memory: { id: string; kind: string; at: string; risk: number | null; verdict: string; outcome: string | null; by: string | null }[];
  investigation: { id: string; status: string; createdAt: string } | null;
  pastInvestigations: { id: string; at: string; risk: number; headline: string }[];
  actions: ActionLogRow[];
}

/* ------------------------------------------------------------ investigation */

export interface CaseNode {
  id: string;
  kind: string;
  label: string;
  sublabel?: string;
  status?: string;
  role?: string;
  stepId?: string;
}

export interface CaseEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  confidence?: number;
  possible?: boolean;
  detail?: string;
}

export interface Evidence {
  id: string;
  kind: string;
  title: string;
  sourceSystem: string;
  recordId?: string;
  date?: string | null;
  quote?: string | null;
  fields?: [string, string | number | null][];
  note?: string | null;
  relationship?: string;
  series?: { week: string; value: number }[];
  url?: string | null;
}

export interface Step {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  title: string;
  status: "running" | "completed" | "failed";
  startedAt: string;
  summary: string;
  ms: number | null;
  queries: { cypher: string; params: Record<string, unknown>; ms: number; rows: number; graph?: string }[];
  origin: string;
  via?: string;
}

export interface VerdictStep {
  n?: number;
  title: string;
  detail: string;
  evidenceIds: string[];
  kind: "observed" | "inferred";
  source: string;
  confidence: number | null;
  inChain: boolean;
}

export interface Verdict {
  accountId: string;
  accountName: string;
  headline: string;
  story: string[];
  risk: number;
  riskLabel: string;
  crmHealthScore: number;
  renewalInDays: number;
  arr: number;
  arrLabel: string;
  chain: VerdictStep[];
  supporting: VerdictStep[];
  counterEvidence: { title: string; detail: string; evidenceIds: string[] }[];
  caveats: string[];
  factors: Factor[];
  bugId: string | null;
  blastRadius?: { accounts: number; arr: number; arrLabel: string; names: string[] };
  playbook?: { id: string; name: string; steps: string[]; outcome: string; workedFor: string[]; doc: string | null; docId: string | null };
  promisesAtRisk: { id: string; text: string; why: string; madeBy: string }[];
  ownersLeaving: { id: string; name: string; lastDay: string; relations: string[] }[];
  memory: { id: string; at: string; verdict: string; outcome: string | null } | null;
  narrativeSource: string;
}

export type ActionState = "proposed" | "approved" | "running" | "succeeded" | "drafted" | "simulated" | "failed" | "needs_attention";

export interface PlanAction {
  id: string;
  type: string;
  title: string;
  summary: string;
  destination: { system: string; mode: string; target: string };
  payload: Record<string, unknown>;
  addresses: string[];
  status: ActionState;
  customerFacing?: boolean;
  result: { message: string; ref?: string | null; url?: string | null } | null;
  approvedBy: string | null;
  approvedAt: string | null;
  executedAt: string | null;
}

export interface FollowUpAnswer {
  id: string;
  question: string;
  intent: string;
  answer: string;
  observed: string[];
  inferred: string[];
  evidenceIds: string[];
  tool: string | null;
  error?: boolean;
}

export interface Investigation {
  id: string;
  accountId: string;
  mode: string;
  modeDetail: string;
  status: "running" | "completed" | "failed";
  createdAt: string;
  completedAt: string | null;
  steps: Step[];
  graph: { nodes: CaseNode[]; edges: CaseEdge[] };
  evidence: Record<string, Evidence>;
  causal: { nodeIds: string[]; edgeIds: string[] };
  verdict: Verdict | null;
  actions: PlanAction[];
  followups: FollowUpAnswer[];
  lastEventId: number;
}

export interface StreamEvent<T = Record<string, unknown>> {
  id: number;
  type: string;
  ts: string;
  payload: T;
}

/* ------------------------------------------------------------ sales assist */

export interface UpcomingMeeting {
  id: string;
  title: string;
  start: string;
  end: string;
  kind: string;
  recording: string | null;
  accountId: string;
  account: string;
  risk: number;
  crm: number;
  silent: boolean;
  arr: number;
  arrLabel: string;
  startsIn: number;
  attendees: { id: string; name: string; internal: boolean }[];
}

export interface Brief {
  meeting: { id: string; title: string; start: string; end: string; kind: string; recording: string | null; url: string; startsIn: number; host: { id: string; name: string } | null };
  account: {
    id: string;
    name: string;
    arr: number;
    arrLabel: string;
    plan: string;
    renewalDate: string;
    renewalInDays: number;
    stage: string;
    crm: number;
    risk: number;
    silent: boolean;
    factors: Factor[];
    wallet: string;
  };
  attendees: { id: string; name: string; title: string; internal: boolean; leaving: boolean; since: string | null; replaced: string | null }[];
  history: { id: string; title: string; date: string; summary: string[] }[];
  openIssues: { bugId: string; title: string; status: string; priority: string; owner: string; tickets: number; workaround: string | null }[];
  promises: PromiseRow[];
  roadmap: { id: string; title: string; status: string; eta: string; originally: string; guidance: string }[];
  experts: { id: string; name: string; role: string; why: string; about: string; leaving: boolean }[];
  goals: string[];
  questions: string[];
  dont: string[];
  signals: { type: string; quote: string; speaker: string; date: string }[];
  generatedAt: string;
  sources: string[];
}

export interface CallCard {
  id: string;
  kind: "answer" | "roadmap" | "bug" | "objection" | "expert" | "promise" | "risk" | "consent";
  tone: "neutral" | "amber" | "red";
  title: string;
  body: string;
  source: { label: string; kind: string; id: string | null; url?: string | null } | null;
  queries: { cypher: string; ms: number; rows: number }[];
  segment: number;
  t: number;
  speaker: string;
  latencyMs: number;
  endToEndMs?: number;
  copy?: string;
  action?: { kind: "ping"; to: string; toId: string; slack: string | null; message: string };
  pinged?: { status: string; message: string };
  promise?: { text: string; due: string; madeBy: string };
  /** Expert cards: shortest working path from the rep to the expert (shortestPath over shared work). */
  path?: { hops: { label: string; id: string; name: string }[]; length: number; summary: string } | null;
}

export interface Segment {
  i: number;
  t: number;
  speaker_email: string;
  speaker_name: string;
  text: string;
  internal: boolean;
  /** Index in the recording (replayed lines only), used to play that line's audio. */
  r?: number;
  /** Typed or spoken in Relay during a live call. */
  typed?: boolean;
}

export interface CallResult {
  meetingId: string;
  notes: string;
  overview: string[];
  promises: { id: string; text: string; due: string; madeBy: string; quote: string; about: { kind: string; id: string } | null }[];
  superseded: { id: string; text: string }[];
  signals: { type: string; quote: string }[];
  actions: PlanAction[];
  health: { before: number | null; after: number; factors: Factor[]; hint: string };
  ms: number;
}

export interface CallSession {
  id: string;
  meetingId: string;
  title: string;
  accountId: string;
  account: string;
  status: "ready" | "live" | "ended" | "summarised" | "failed";
  speed: number;
  startedAt: string | null;
  endedAt: string | null;
  duration: number;
  consent: boolean;
  source: string;
  transcript: Segment[];
  cards: CallCard[];
  result: CallResult | null;
  lastEventId: number;
}

export interface MeetingRecord {
  meeting: { id: string; title: string; date: string; status: string; notes: string | null; recording: string | null; transcript: { speaker: string | null; speakerName?: string; t?: number; text: string }[] };
  accountId: string;
  account: string;
  promises: { id: string; text: string; due: string; status: string }[];
  call: CallSession | null;
}

/* ------------------------------------------------------------ under the hood */

export interface GraphStats {
  role: string;
  name: string;
  graph: string;
  company: { name: string; tagline: string } | null;
  nodes: number;
  edges: number;
  labels: { label: string; n: number }[];
  relationships: { type: string; n: number }[];
}

export interface Meter {
  qps: number;
  total: number;
  p50ms: number | null;
  p95ms: number | null;
}

export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2).replace(/\.?0+$/, "")} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1).replace(/\.0$/, "")}L`;
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

export function riskTone(risk: number): "risk" | "warn" | "covered" {
  return risk >= 60 ? "risk" : risk >= 40 ? "warn" : "covered";
}

export function crmTone(crm: number): "risk" | "warn" | "covered" {
  return crm >= 70 ? "covered" : crm >= 50 ? "warn" : "risk";
}

export function timeIST(iso: string, opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" }) {
  return new Date(iso).toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", ...opts });
}

export function dayIST(iso: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }) {
  return new Date(iso).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", ...opts });
}

export function mmss(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** "Good morning" etc. by the demo clock (an IST timestamp from the session), not the viewer's clock. */
export function greeting(demoNow?: string) {
  const h = demoNow ? Number(demoNow.slice(11, 13)) : new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}
