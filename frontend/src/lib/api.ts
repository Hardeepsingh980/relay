// Thin client for the Relay API. The acting persona travels in X-Relay-Persona.

export const API_BASE = process.env.NEXT_PUBLIC_RELAY_API ?? process.env.NEXT_PUBLIC_BATON_API ?? "http://localhost:8020";

const PERSONA_KEY = "relay.persona";

/** The demo persona this browser acts as ("" = the company's default persona). */
export function currentPersona(): string {
  try {
    return localStorage.getItem(PERSONA_KEY) || "";
  } catch {
    return "";
  }
}

export function storePersona(id: string) {
  try {
    localStorage.setItem(PERSONA_KEY, id);
  } catch {
    /* private mode: persona falls back to the manager */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Relay-Persona": currentPersona(),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    credentials: "include",
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.error || body.detail || message;
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export const fetcher = <T,>(path: string) => request<T>(path);

export const api = {
  request: <T,>(path: string, init?: RequestInit) => request<T>(path, init),
  patch: <T,>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
};

export const enc = encodeURIComponent;

export interface User {
  id: string;
  name: string;
  email: string;
  createdAt?: string;
  avatarUrl?: string | null;
  jobRole?: string | null;
  defaultPersona?: string | null;
  onboardedAt?: string | null;
  hasPassword?: boolean;
  google?: boolean;
  /** Signed in as a teammate from the team picker, inside this browser's own copy of the workspace. */
  sandbox?: boolean;
}

export interface TeamMember {
  id: string;
  name: string;
  team: string;
  persona: string;
  home: string;
  role: string;
  task: string;
}

export interface TeamPreview {
  nodes: number;
  relationships: number;
  counts: Record<string, number>;
  silent: { name: string; crm: number; risk: number; arr: number }[];
  onlyRahul: number;
  ms: number;
}

/** GET /api/public/graph: a real slice of the sample company's graph, for the landing page. */
export interface LandingGraph {
  nodes: { id: number; type: string; name: string; key: string | null }[];
  edges: { s: number; t: number; type: string }[];
  stories: { agent: string; path: number[]; text: string; chip: string }[];
  colors: Record<string, string>;
  preview: TeamPreview;
}

export const publicApi = {
  graph: () => request<LandingGraph>("/api/public/graph"),
};

export interface WorkspaceInfo {
  id: string;
  name: string;
  slug?: string;
  createdAt?: string;
  demoData: boolean;
  tenant?: string;
  company?: string;
  role: "owner" | "admin" | "member" | null;
}

export interface Me {
  user: User;
  workspace: WorkspaceInfo | null;
  workspaces: WorkspaceInfo[];
}

export const authApi = {
  me: () => request<{ user: User; workspace: WorkspaceInfo | null }>("/api/auth/me"),
  providers: () => request<{ password: boolean; google: boolean }>("/api/auth/providers"),
  signIn: (email: string, password: string, invite?: string | null) =>
    request<{ user: User; joined: WorkspaceInfo | null }>("/api/auth/sign-in", { method: "POST", body: JSON.stringify({ email, password, invite }) }),
  signUp: (name: string, email: string, password: string, invite?: string | null) =>
    request<{ user: User; joined: WorkspaceInfo | null }>("/api/auth/sign-up", {
      method: "POST",
      body: JSON.stringify({ name, email, password, invite }),
    }),
  signOut: () => request<{ ok: boolean }>("/api/auth/sign-out", { method: "POST" }),
  team: () => request<{ company: string; members: TeamMember[]; preview: TeamPreview }>("/api/auth/team"),
  teamSignIn: (personId: string) =>
    request<{ user: User; member: TeamMember }>("/api/auth/team", { method: "POST", body: JSON.stringify({ personId }) }),
  googleUrl: (next?: string | null, invite?: string | null) =>
    `${API_BASE}/api/auth/google/start?${new URLSearchParams({ next: next || "/home", ...(invite ? { invite } : {}) })}`,
};

/** Only allow same-site relative redirects after sign-in. */
export function safeNext(next: string | null | undefined, fallback = "/home") {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}

export function sourcePath(label: string, id: string) {
  return `/api/sources/${enc(label)}/${id.split("/").map(enc).join("/")}`;
}
