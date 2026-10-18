// Shapes returned by the Relay FastAPI backend (knowledge layer). Account Health and Sales Assist live in relay.ts.

export type ItemType = "System" | "Account" | "Decision" | "Workaround";
export type RiskState = "at_risk" | "assigned" | "captured" | "verified" | "dismissed" | "blocked";

export interface Person {
  id: string;
  name: string;
  role: string;
  team: string;
  status: "active" | "joining" | "left";
  startDate?: string | null;
  lastDay?: string | null;
  email?: string;
}

export interface Persona extends Person {
  persona: "manager" | "leaver" | "joiner" | "head_cs" | "csm";
  home: string;
}

export type SourceKind =
  | "slack"
  | "doc"
  | "jira"
  | "meeting"
  | "github"
  | "handover"
  | "support"
  | "crm"
  | "conversation"
  | "roadmap"
  | "promise"
  | "other";

export interface SourceRef {
  kind: SourceKind;
  id: string;
  nodeLabel: string;
  title: string;
  label: string;
  at?: string | null;
  excerpt?: string | null;
  url?: string | null;
  freshness?: string | null;
  highlight?: string | null;
  via?: string;
  tag?: string;
}

export interface SourceDetail extends SourceRef {
  available: boolean;
  availability: string;
  thread?: { id: string; text: string; at: string; author: string; external: boolean; org: string; focus: boolean }[];
  body?: string;
  author?: string | null;
  authorStatus?: string | null;
  staleReason?: string | null;
  updatedAt?: string;
  transcript?: { speaker: string; text: string }[];
  notes?: string;
  status?: string;
  assignee?: string | null;
  comments?: { author_email: string; created: string; body: string }[];
  description?: string;
  repo?: string;
  message?: string;
  question?: string;
  answer?: string;
}

export interface Alternate {
  id: string;
  name: string;
  score: number;
  status: string;
  credible: boolean;
  basis: string;
  note?: string | null;
}

export interface Evidence {
  facts: string[];
  sources: SourceRef[];
  alternates: Alternate[];
  link: { score: number | null; lastSeen: string | null; stale: boolean };
}

export interface Suggestion {
  id: string;
  name: string;
  role: string;
  score: number;
  reason: string;
  confidence: "high" | "medium" | "low";
  signals: { direct: number; context: number; reviews: number; sameTeam: boolean };
}

export interface Knowledge {
  id: string;
  question: string | null;
  answer: string;
  originalAnswer?: string;
  capturedAt: string;
  editedAt?: string | null;
  verifiedAt?: string | null;
  verifiedBy?: string | null;
  authorId?: string;
  authorName?: string;
  itemId?: string;
  context?: SourceRef | null;
}

export interface RiskItem {
  id: string;
  itemId: string;
  type: ItemType;
  title: string;
  state: RiskState;
  priority: number;
  order: number;
  subtitle?: string | null;
  criticality?: string | null;
  about: string[];
  evidence: Evidence;
  suggestions: Suggestion[];
  suggestedId?: string | null;
  successor?: { id: string; name: string; role: string } | null;
  skipped: boolean;
  dismissReason?: string | null;
  dismissedBy?: string | null;
  note?: string | null;
  question?: { context: string; prompt: string; mode: string; source: SourceRef | null } | null;
  knowledge?: Knowledge | null;
  updatedAt?: string;
}

export interface Coverage {
  handoverId: string;
  total: number;
  atRisk: number;
  byState: Record<RiskState, number>;
  complete: boolean;
  assignedOrBetter: number;
}

export interface HandoverMeta {
  id: string;
  leaverId: string;
  joinerId?: string | null;
  managerId: string;
  lastDay: string;
  status: "created" | "analyzing" | "active" | "closed";
  createdAt: string;
  analyzedAt?: string | null;
  analyses?: number;
  closedAt?: string | null;
}

export interface Handover {
  handover: HandoverMeta;
  leaver: Person;
  joiner: Person | null;
  manager: Person;
  riskItems: RiskItem[];
  coverage: Coverage;
  thinCoverage: { type: ItemType; id: string; title: string; remaining: string }[];
}

export interface HandoverSummary {
  id: string;
  status: string;
  lastDay: string;
  leaver: Person;
  joiner: Person | null;
  coverage: Coverage;
}

export interface RiskPerson {
  id: string;
  name: string;
  role: string;
  team: string;
  unique: number;
  byType: Partial<Record<ItemType, number>>;
}

export interface Home {
  singlePointsOfFailure: number;
  byType: Partial<Record<ItemType, number>>;
  people: RiskPerson[];
  activeHandovers: HandoverSummary[];
  closedHandovers: HandoverSummary[];
}

export interface PersonRow extends Person {
  unique: number;
  byType: Partial<Record<ItemType, number>>;
}

export interface Profile {
  person: Person;
  manager: { id: string; name: string } | null;
  knowsAbout: { id: string; name: string; type: ItemType; score: number; unique: boolean; basis?: string | null }[];
  uniqueCount: number;
  handover: { id: string; status: string; lastDay: string } | null;
  incomingJoiners: { id: string; name: string; role: string; startDate: string }[];
}

export interface GraphNode {
  id: string;
  kind: "person" | "system" | "customer" | "decision" | "workaround";
  name: string;
  role?: string | null;
  risk?: "unique" | "shared" | "thin" | "covered" | null;
  state?: RiskState | null;
  riskId?: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  score: number | null;
  fromLeaver?: boolean;
  handover?: boolean;
}

export interface GraphView {
  nodes: GraphNode[];
  edges: GraphEdge[];
  relationships: string[];
}

export interface InterviewQuestion {
  riskId: string;
  itemId: string;
  type: ItemType;
  title: string;
  state: RiskState;
  skipped: boolean;
  context: string;
  prompt: string;
  mode: string;
  source: SourceRef | null;
  answer: string | null;
  sampleAnswer: string | null;
}

export interface Interview {
  handover: HandoverMeta;
  leaver: Person;
  joiner: Person | null;
  questions: InterviewQuestion[];
  progress: { answered: number; skipped: number; total: number; next: number | null };
}

export interface MeetPerson {
  id: string;
  name: string;
  role: string;
  team: string;
  lastDay?: string | null;
  centrality: number;
  reason: string;
  leaving?: boolean;
  urgent?: boolean;
  links: { id: string; name: string; label: string; rel: string; score: number }[];
  taking: string[];
}

export interface KnowledgeCard {
  id: string;
  system: string | null;
  itemId: string;
  itemType: ItemType;
  itemTitle: string;
  question: string | null;
  answer: string;
  author: string;
  capturedAt: string;
  capturedLabel: string;
  verified: boolean;
  verifiedBy?: string | null;
  sources: SourceRef[];
}

export interface ChecklistItem {
  id: string;
  kind: "doc" | "people" | "ticket";
  label: string;
  targetId: string | null;
  targetLabel: string | null;
  note: string | null;
  done: boolean;
  doneAt?: string | null;
  familiarWith?: string | null;
}

export interface DayOne {
  person: Person;
  handover: { id: string; status: string; lastDay: string } | null;
  leaver?: Person;
  team?: string;
  services?: {
    id: string;
    name: string;
    summary: string;
    criticality: string;
    repo: string | null;
    knowledge: number;
    state: RiskState;
    successor: { id: string; name: string; role: string } | null;
    openTickets: { id: string; title: string; status: string; owner: string | null }[];
  }[];
  decisions?: {
    id: string;
    summary: string;
    decidedAt: string;
    decidedLabel: string | null;
    rationaleStatus: string;
    systems: string[];
    knowledge: number;
    inherited: boolean;
    state: RiskState | null;
  }[];
  meet?: MeetPerson[];
  fromLeaver?: KnowledgeCard[];
  checklist?: ChecklistItem[];
  familiarWith?: string[];
  graph?: GraphView;
}

export interface PathStep {
  kind: string;
  label: string;
  id?: string;
  nodeLabel?: string;
  edge?: string;
}

export interface AskAnswer {
  answer: string;
  segments: ({ text: string } | { source: string })[];
  sources: (SourceRef & { tag: string })[];
  path: PathStep[];
  mode: "llm" | "extractive" | "graph" | "no-evidence" | "empty";
  confidence?: "high" | "medium" | "low";
  supported?: boolean;
  conflicts: { source: SourceRef; note: string }[];
  freshness: { newest: string | null; label: string | null } | null;
  followups: string[];
}

export type ActionStatus = "proposed" | "running" | "succeeded" | "failed" | "simulated";

export interface Action {
  id: string;
  type: "calendar.intro" | "ticket.reassign" | "email.draft";
  title: string;
  status: ActionStatus;
  mode: "live" | "simulated";
  destination: string;
  handoverId?: string | null;
  riskId?: string | null;
  createdAt: string;
  approvedBy?: string | null;
  approvedAt?: string | null;
  finishedAt?: string | null;
  payload: Record<string, unknown>;
  result: { message: string; url?: string; externalId?: string } | null;
}

export interface DocProposal {
  id: string;
  docId: string;
  title: string;
  summary: string;
  diff: string;
  status: "proposed" | "applied";
  mode: "llm" | "template";
  createdAt: string;
  updatedAt: string;
  approvedBy?: string | null;
  approvedAt?: string | null;
  staleReason?: string | null;
  knowledgeIds: string[];
}

export interface Integration {
  id: string;
  name: string;
  state: "Connected" | "Disconnected" | "Simulated" | "Pending" | "Succeeded" | "Failed";
  mode: "live" | "simulated" | "synthetic";
  detail?: string;
}

export interface JourneyStep {
  id: string;
  group: string;
  label: string;
  done: boolean;
  href: string;
  persona?: string;
  ask?: string;
}

export interface Journey {
  steps: JourneyStep[];
  done: number;
  total: number;
  next: string | null;
  dismissed: boolean;
  title?: string;
}

export interface Connection {
  id: string;
  name: string;
  kind: "source" | "action" | "ai";
  category: string;
  description: string;
  status: "connected" | "disconnected";
  mode: "demo" | "live" | "server" | null;
  connectedAt?: string | null;
  account?: string | null;
  demo?: string;
  live: boolean;
  available?: boolean;
  liveNote?: string | null;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string | null;
  role: "owner" | "admin" | "member";
  joinedAt: string;
}

export interface PendingInvite {
  id: string;
  email: string;
  role: "admin" | "member";
  createdAt: string;
  invitedBy: string | null;
}

export interface Session {
  personas: Persona[];
  demo: { synthetic: boolean; company: string; tenant: string; tagline: string; now: string; dataAsOf: string; note: string };
  modules: { accountHealth: boolean; salesAssist: boolean; knowledge: boolean; ask: boolean };
  suggestions: string[];
  integrations: Integration[];
  llm: { enabled: boolean; model: string; embedModel: string; extractor: string };
}

export interface BatonEvent<T = Record<string, unknown>> {
  eventId: string;
  type: string;
  timestamp: string;
  payload: T;
}
