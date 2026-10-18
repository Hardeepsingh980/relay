"use client";

import Graph from "graphology";
import type FA2LayoutSupervisor from "graphology-layout-forceatlas2/worker";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type Sigma from "sigma";
import useSWR from "swr";
import {
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Eye,
  Layers,
  Loader2,
  Maximize2,
  MessageCircleQuestion,
  Minus,
  Play,
  Plus,
  Search,
  X,
} from "lucide-react";

import { useApp } from "@/components/app-provider";
import { enc } from "@/lib/api";
import { cn } from "@/lib/utils";

type Layer = "knowledge" | "full";

interface GNode {
  id: string;
  type: string;
  name: string;
  degree: number;
  extra: Record<string, string | number | boolean> | null;
}
interface GEdge {
  s: string;
  t: string;
  type: string;
}
interface GType {
  type: string;
  label: string;
  group: string;
  color: string;
  count: number;
}
interface Overview {
  layer: Layer;
  graph: string;
  nodes: GNode[];
  edges: GEdge[];
  types: GType[];
  stats: { totalNodes: number; totalRelationships: number; shownNodes: number; shownEdges: number; ms: number; dbMs: number };
}
interface Neighbour {
  id: string;
  type: string;
  name: string;
}
interface NodeDetail {
  id: string;
  type: string;
  name: string;
  degree: number;
  props: Record<string, unknown>;
  aggregates: Record<string, number>;
  neighbours: { rel: string; dir: "in" | "out"; total: number; items: Neighbour[] }[];
  ms: number;
}

/** Node attributes. `kind`, not `type`: sigma reads `type` to pick a WebGL program. */
interface NodeAttrs {
  x: number;
  y: number;
  size: number;
  color: string;
  dim: string;
  label: string;
  kind: string;
  typeLabel: string;
  name: string;
  degree: number;
}
interface EdgeAttrs {
  color: string;
  hot: string;
  size: number;
  rel: string;
}
type KGraph = Graph<NodeAttrs, EdgeAttrs>;

/** Mutable view state read by the sigma reducers (kept out of React to avoid re-renders on hover). */
interface ViewState {
  hovered: string | null;
  selected: string | null;
  near: Set<string>;
  hidden: Set<string>;
}

const SIZE_FACTOR: Record<string, number> = {
  Person: 1.15,
  System: 1.25,
  Team: 1.1,
  Account: 1,
  Feature: 1.1,
  Channel: 0.9,
  Contact: 0.7,
  Bug: 0.9,
  Ticket: 0.62,
  Task: 0.6,
  Risk: 0.72,
  Doc: 0.85,
  Meeting: 0.85,
  Message: 0.48,
  Commit: 0.5,
  PullRequest: 0.58,
  Signal: 0.68,
  Conversation: 0.62,
};
const QUIET = new Set(["Message", "Commit", "PullRequest", "Ticket", "Task", "Conversation", "Signal"]);
const SEARCH_FIRST = ["Person", "Account", "System", "Decision", "Feature", "Team", "Playbook", "Workaround", "Bug", "Contact"];
const fmt = (n: number) => n.toLocaleString("en-IN");

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
const rgba = (hex: string, a: number) => {
  const [r, g, b] = rgb(hex);
  return `rgba(${r},${g},${b},${a})`;
};
/** Edge colours are blended premultiplied by sigma, so scale the channels by alpha ourselves. */
const premul = (hex: string, a: number) => {
  const [r, g, b] = rgb(hex);
  return `rgba(${Math.round(r * a)},${Math.round(g * a)},${Math.round(b * a)},${a})`;
};
/** "People" -> "Person", "Roadmap items" -> "Roadmap item". */
const one = (label: string) => (label === "People" ? "Person" : label.replace(/s$/, ""));
const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

function buildGraph(data: Overview): KGraph {
  const g: KGraph = new Graph<NodeAttrs, EdgeAttrs>({ type: "directed", multi: false, allowSelfLoops: false });
  const color: Record<string, string> = {};
  const label: Record<string, string> = {};
  const sector: Record<string, [number, number]> = {};
  let acc = 0;
  for (const t of data.types) {
    color[t.type] = t.color;
    label[t.type] = one(t.label);
    sector[t.type] = [(acc / data.nodes.length) * Math.PI * 2, (t.count / data.nodes.length) * Math.PI * 2];
    acc += t.count;
  }
  const full = data.layer === "full";
  for (const n of data.nodes) {
    const [start, span] = sector[n.type] ?? [0, Math.PI * 2];
    // Seed each type in its own slice of a small disc: the layout then blooms it outward.
    const a = start + Math.random() * span;
    const r = 4 + Math.sqrt(Math.random()) * 26;
    const c = color[n.type] ?? "#8a93a6";
    const quiet = QUIET.has(n.type);
    const size = Math.min(20, (SIZE_FACTOR[n.type] ?? 1) * (1.1 + 1.3 * Math.log2(1 + n.degree)));
    g.addNode(n.id, {
      x: Math.cos(a) * r,
      y: Math.sin(a) * r,
      size: full && quiet ? size * 0.85 : size,
      color: quiet ? rgba(c, 0.72) : c,
      dim: rgba(c, 0.09),
      label: clip(n.name, 44),
      kind: n.type,
      typeLabel: label[n.type] ?? n.type,
      name: n.name,
      degree: n.degree,
    });
  }
  const alpha = full ? 0.055 : 0.11;
  for (const e of data.edges) {
    if (e.s === e.t || !g.hasNode(e.s) || !g.hasNode(e.t) || g.hasEdge(e.s, e.t) || g.hasEdge(e.t, e.s)) continue;
    const c = color[g.getNodeAttribute(e.s, "kind")] ?? "#8a93a6";
    g.addEdge(e.s, e.t, { color: premul(c, alpha), hot: premul(c, 0.6), size: 0.6, rel: e.type });
  }
  return g;
}

const KEY_LABEL: Record<string, string> = {
  arr: "ARR",
  mrr: "MRR",
  crmHealthScore: "CRM health",
  crmHealthSource: "CRM health source",
  detectiveRisk: "Relay risk",
  isChampion: "Champion",
  etaLabel: "ETA",
  eta: "ETA date",
  usageWeeks: "Usage weeks",
  unpaidInvoices: "Unpaid invoices",
};
function humanKey(k: string) {
  if (KEY_LABEL[k]) return KEY_LABEL[k];
  const s = k.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// How an incoming relationship reads from the selected node's side.
const INCOMING: Record<string, string> = {
  MEMBER_OF: "Members",
  REPORTS_TO: "Direct reports",
  OWNED_BY_TEAM: "Systems owned",
  OWNS: "Owned by",
  WORKS_AT: "People here",
  SUCCEEDED: "Succeeded by",
  IN_CHANNEL: "Messages",
  SENT: "Sent by",
  REPLY_TO: "Replies",
  AUTHORED: "Authored by",
  DOCUMENTS: "Documented in",
  OWNED_BY: "Owns",
  REPORTED_BY: "Reported",
  CONCERNS: "Tickets about this",
  ATTENDED: "Attended by",
  WITH: "Meetings",
  IN_REPO: "Commits and pull requests",
  PART_OF: "Commits",
  REVIEWED: "Reviewed by",
  MENTIONS: "Mentioned in",
  MANAGES: "Managed by",
  TECH_CONTACT_FOR: "Tech contact",
  SERVED_BY: "Serves features",
  USES: "Used by",
  AFFECTS: "Affected by",
  RAISED: "Raised by",
  ABOUT_FEATURE: "Tickets",
  SYMPTOM_OF: "Symptoms",
  ASSIGNED_TO: "Assigned",
  WITH_ACCOUNT: "Conversations",
  PARTICIPATED_IN: "Participants",
  EXPRESSES: "Expressed in",
  FOR_FEATURE: "Roadmap items",
  INVITED_TO: "Invited",
  HOSTS: "Hosted by",
  PRODUCED: "Produced by",
  TO: "Promises",
  MADE: "Made by",
  DEPENDS_ON: "Depended on by",
  SOURCED_FROM: "Source of",
  WORKED_FOR: "Playbooks",
  FOR_ACCOUNT: "Past saves",
  RAN: "Run by",
  ABOUT: "Decisions and workarounds",
  OBSOLETES: "Made obsolete by",
  DECIDED: "Decided by",
  KNOWS: "Known by",
  ON: "Risks",
  CAUSED_BY: "Caused",
};
function humanRel(rel: string, dir: "in" | "out") {
  if (dir === "in" && INCOMING[rel]) return INCOMING[rel];
  const r = rel.toLowerCase().replace(/_/g, " ");
  return r.charAt(0).toUpperCase() + r.slice(1);
}
function showValue(v: unknown): string {
  if (typeof v === "number") return v.toLocaleString("en-IN");
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

const TEXT_KEYS = ["summary", "description", "text", "rationale", "verdict", "outcome", "detail", "quote", "purpose", "body", "notes"];
const SKIP_KEYS = new Set(["id", "name", "title", "url", "aliases", "transcript", "comments", "steps", "riskFactors", "labels", "slackId", ...TEXT_KEYS]);

function askFor(d: NodeDetail): string {
  switch (d.type) {
    case "Person":
      return `What does ${d.name} know that nobody else does?`;
    case "System":
      return `Who knows ${d.name} best?`;
    case "Account":
      return `Why is ${d.name} at risk?`;
    case "Bug":
      return `Which accounts are hit by ${d.name.split(" · ")[0]}?`;
    default:
      return `What do we know about ${clip(d.name, 80)}?`;
  }
}

function pageFor(d: NodeDetail): { href: string; label: string } | null {
  const key = d.id.split(":").slice(1).join(":");
  if (d.type === "Person") return { href: `/people/${enc(key)}`, label: "Open profile" };
  if (d.type === "Account") return { href: `/accounts/${enc(key)}`, label: "Open account" };
  if (d.type === "Meeting") return { href: `/meetings/${enc(key)}`, label: "Open meeting" };
  return null;
}

export function GraphClient() {
  const params = useSearchParams();
  const { session, openAsk } = useApp();
  const [layer, setLayer] = useState<Layer>(params.get("layer") === "full" ? "full" : "knowledge");
  const { data, error, isLoading } = useSWR<Overview>(`/api/graph/overview?layer=${layer}`, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    revalidateIfStale: false,
    keepPreviousData: true,
  });

  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma<NodeAttrs, EdgeAttrs> | null>(null);
  const layoutRef = useRef<FA2LayoutSupervisor | null>(null);
  const graphRef = useRef<KGraph | null>(null);
  const timerRef = useRef<number | null>(null);
  const view = useRef<ViewState>({ hovered: null, selected: null, near: new Set(), hidden: new Set() });
  const libs = useRef<{
    FA2: typeof FA2LayoutSupervisor;
    infer: (g: KGraph) => Record<string, unknown>;
  } | null>(null);

  const [ready, setReady] = useState(false);
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  // null: open on wide screens, closed on phones (decided in CSS, so server and client agree).
  const [legendOpen, setLegendOpen] = useState<boolean | null>(null);

  const { data: detail, isLoading: detailLoading } = useSWR<NodeDetail>(selected ? `/api/graph/node/${enc(selected)}` : null, {
    revalidateOnFocus: false,
  });

  // Load sigma, the glow program and the ForceAtlas2 worker on the client only.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      import("sigma"),
      import("./graph-programs"),
      import("graphology-layout-forceatlas2/worker"),
      import("graphology-layout-forceatlas2"),
    ]).then(([sigmaMod, programs, worker, fa2]) => {
      if (cancelled || !containerRef.current) return;
      const state = view.current;
      const renderer = new sigmaMod.default<NodeAttrs, EdgeAttrs>(new Graph<NodeAttrs, EdgeAttrs>(), containerRef.current, {
        allowInvalidContainer: true,
        defaultNodeType: "glow",
        nodeProgramClasses: { glow: programs.GlowNodeProgram },
        defaultDrawNodeLabel: programs.drawLabel,
        defaultDrawNodeHover: programs.drawHover,
        labelFont: "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif",
        labelRenderedSizeThreshold: 10,
        labelDensity: 0.5,
        labelGridCellSize: 110,
        minEdgeThickness: 0.6,
        stagePadding: 64,
        zIndex: true,
        minCameraRatio: 0.03,
        maxCameraRatio: 6,
        nodeReducer: (node, attrs) => {
          if (state.hidden.has(attrs.kind)) return { ...attrs, hidden: true };
          const focus = state.hovered ?? state.selected;
          if (!focus) return attrs;
          if (node === focus) return { ...attrs, highlighted: true, forceLabel: true, zIndex: 3 };
          if (state.near.has(node)) return { ...attrs, zIndex: 2, forceLabel: state.near.size <= 30 };
          return { ...attrs, color: attrs.dim, label: "", zIndex: 0 };
        },
        edgeReducer: (edge, attrs) => {
          const g = graphRef.current;
          if (!g) return attrs;
          const s = g.source(edge);
          const t = g.target(edge);
          if (state.hidden.size && (state.hidden.has(g.getNodeAttribute(s, "kind")) || state.hidden.has(g.getNodeAttribute(t, "kind")))) {
            return { ...attrs, hidden: true };
          }
          const focus = state.hovered ?? state.selected;
          if (!focus) return attrs;
          if (s === focus || t === focus) return { ...attrs, color: attrs.hot, size: 1.3, zIndex: 1 };
          return { ...attrs, hidden: true };
        },
      });
      renderer.on("enterNode", ({ node }) => {
        state.hovered = node;
        state.near = new Set(renderer.getGraph().neighbors(node));
        if (containerRef.current) containerRef.current.style.cursor = "pointer";
        renderer.refresh({ skipIndexation: true });
      });
      renderer.on("leaveNode", () => {
        state.hovered = null;
        state.near = state.selected ? new Set(renderer.getGraph().neighbors(state.selected)) : new Set();
        if (containerRef.current) containerRef.current.style.cursor = "";
        renderer.refresh({ skipIndexation: true });
      });
      sigmaRef.current = renderer;
      libs.current = {
        FA2: worker.default,
        infer: (g) => fa2.default.inferSettings(g) as Record<string, unknown>,
      };
      setReady(true);
    });
    return () => {
      cancelled = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      layoutRef.current?.kill();
      sigmaRef.current?.kill();
      sigmaRef.current = null;
    };
  }, []);

  const runLayout = useCallback((ms: number) => {
    const g = graphRef.current;
    const L = libs.current;
    if (!g || !L) return;
    layoutRef.current?.kill();
    if (timerRef.current) window.clearTimeout(timerRef.current);
    const big = g.order > 3000;
    // Strong gravity keeps the whole graph round; hubs gather their leaves into bright clusters.
    const layout = new L.FA2(g, {
      settings: {
        ...L.infer(g),
        barnesHutOptimize: g.order > 800,
        barnesHutTheta: big ? 0.8 : 0.6,
        linLogMode: false,
        outboundAttractionDistribution: false,
        strongGravityMode: true,
        gravity: 0.4,
        scalingRatio: 10,
        slowDown: 2.5,
        adjustSizes: false,
      },
    });
    layoutRef.current = layout;
    layout.start();
    setRunning(true);
    timerRef.current = window.setTimeout(() => {
      layout.stop();
      setRunning(false);
    }, ms);
  }, []);

  /** Fitted camera, nudged right on wide screens so the left-hand panels don't cover the graph. */
  const home = useCallback(() => {
    const renderer = sigmaRef.current;
    const base = { x: 0.5, y: 0.5, angle: 0, ratio: 1 };
    if (!renderer) return base;
    const { width, height } = renderer.getDimensions();
    if (width < 900) return base;
    const shift = Math.min(90, (width - height) / 2);
    const a = renderer.viewportToFramedGraph({ x: width / 2, y: height / 2 }, { cameraState: base });
    const b = renderer.viewportToFramedGraph({ x: width / 2 - shift, y: height / 2 }, { cameraState: base });
    return { ...base, x: base.x + (b.x - a.x) };
  }, []);

  const select = useCallback((id: string | null, fly = false) => {
    const renderer = sigmaRef.current;
    const g = graphRef.current;
    const state = view.current;
    if (!renderer || !g) return;
    const node = id && g.hasNode(id) ? id : null;
    state.selected = node;
    state.near = node ? new Set(g.neighbors(node)) : new Set();
    setSelected(node);
    renderer.refresh({ skipIndexation: true });
    if (node && fly) {
      const d = renderer.getNodeDisplayData(node);
      const camera = renderer.getCamera();
      if (d) camera.animate({ x: d.x, y: d.y, ratio: Math.min(camera.ratio, 0.32) }, { duration: 700, easing: "cubicInOut" });
    }
  }, []);

  // Build the graph for the current layer and let it settle.
  useEffect(() => {
    const renderer = sigmaRef.current;
    if (!ready || !renderer || !data) return;
    const g = buildGraph(data);
    graphRef.current = g;
    const state = view.current;
    state.hovered = null;
    state.near = state.selected && g.hasNode(state.selected) ? new Set(g.neighbors(state.selected)) : new Set();
    if (state.selected && !g.hasNode(state.selected)) state.selected = null;
    renderer.setGraph(g);
    renderer.refresh(); // index now, so the camera maths below sees this graph's extent
    renderer.setSetting("hideEdgesOnMove", data.layer === "full");
    renderer.setSetting("labelRenderedSizeThreshold", data.layer === "full" ? 11 : 9);
    const camera = renderer.getCamera();
    const fit = home();
    camera.setState({ ...fit, ratio: 2.4 });
    camera.animate(fit, { duration: 4200, easing: "cubicOut" });
    runLayout(data.layer === "full" ? 6000 : 5000);
    const focus = params.get("focus");
    let t: number | undefined;
    if (focus && g.hasNode(focus)) t = window.setTimeout(() => select(focus, true), 5200);
    return () => {
      if (t) window.clearTimeout(t);
      layoutRef.current?.kill();
      layoutRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, data, runLayout, select, home]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && view.current.selected) select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [select]);

  // Click handling needs the latest `select`; register once sigma exists.
  useEffect(() => {
    const renderer = sigmaRef.current;
    if (!ready || !renderer) return;
    const onClick = ({ node }: { node: string }) => select(node);
    const onStage = () => select(null);
    renderer.on("clickNode", onClick);
    renderer.on("clickStage", onStage);
    return () => {
      renderer.off("clickNode", onClick);
      renderer.off("clickStage", onStage);
    };
  }, [ready, select]);

  const toggleType = (type: string) => {
    const next = new Set(view.current.hidden);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    view.current.hidden = next;
    setHidden(next);
    sigmaRef.current?.refresh({ skipIndexation: true });
  };
  const showAll = () => {
    view.current.hidden = new Set();
    setHidden(new Set());
    sigmaRef.current?.refresh({ skipIndexation: true });
  };

  const matches = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term || !data) return [];
    const rank = (n: GNode) => {
      const name = n.name.toLowerCase();
      const pos = SEARCH_FIRST.indexOf(n.type);
      return (name.startsWith(term) ? 0 : 1000) + (pos < 0 ? 100 : pos * 10) - Math.min(n.degree, 999) / 1000;
    };
    return data.nodes
      .filter((n) => n.name.toLowerCase().includes(term) || n.id.slice(n.id.indexOf(":") + 1).toLowerCase().includes(term))
      .sort((a, b) => rank(a) - rank(b))
      .slice(0, 8);
  }, [q, data]);

  const byId = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n])), [data]);
  const typeOf = useMemo(() => Object.fromEntries((data?.types ?? []).map((t) => [t.type, t])), [data]);

  const pick = (n: GNode) => {
    if (hidden.has(n.type)) toggleType(n.type);
    select(n.id, true);
    setQ("");
    setActive(0);
  };

  const zoom = (dir: "in" | "out" | "fit") => {
    const camera = sigmaRef.current?.getCamera();
    if (!camera) return;
    if (dir === "in") camera.animatedZoom({ duration: 300 });
    else if (dir === "out") camera.animatedUnzoom({ duration: 300 });
    else camera.animate(home(), { duration: 600, easing: "quadraticInOut" });
  };

  const company = session?.demo.company ?? "Company";
  const stats = data?.stats;
  const switching = isLoading || (data && data.layer !== layer);

  return (
    <div className="fixed inset-x-0 bottom-16 top-16 z-0 overflow-hidden bg-[#070b14] text-white md:bottom-0 md:left-[232px]">
      {/* Deep space: a soft glow behind the graph and a faint star field. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 48%, rgba(56, 90, 190, 0.20), transparent 70%), radial-gradient(ellipse 50% 40% at 82% 12%, rgba(130, 80, 220, 0.12), transparent 70%), radial-gradient(ellipse 45% 35% at 12% 88%, rgba(20, 160, 170, 0.10), transparent 70%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "radial-gradient(1px 1px at 23px 41px, rgba(255,255,255,0.35), transparent 60%), radial-gradient(1px 1px at 157px 113px, rgba(255,255,255,0.25), transparent 60%), radial-gradient(1px 1px at 91px 190px, rgba(180,200,255,0.3), transparent 60%), radial-gradient(1.5px 1.5px at 211px 27px, rgba(255,255,255,0.2), transparent 60%)",
          backgroundSize: "240px 240px",
        }}
      />
      <div ref={containerRef} className="absolute inset-0" aria-label="Knowledge graph canvas" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 85% 80% at 50% 50%, transparent 60%, rgba(3, 5, 12, 0.65) 100%)" }}
      />

      {/* Title and live stats */}
      <div className="pointer-events-none absolute left-4 top-4 max-w-[calc(100%-2rem)] md:left-5 md:top-5">
        <div className="pointer-events-auto rounded-2xl border border-white/10 bg-[#0b1222]/70 px-4 py-3 shadow-[0_10px_40px_rgba(0,0,0,0.45)] backdrop-blur-md">
          <h1 className="text-[15px] font-semibold tracking-[-0.2px] text-white">{company} knowledge graph</h1>
          {stats ? (
            <p className="mt-1 text-[12px] leading-relaxed text-white/60">
              <span className="text-white/90">{fmt(stats.totalNodes)}</span> nodes ·{" "}
              <span className="text-white/90">{fmt(stats.totalRelationships)}</span> relationships in FalkorDB
              <br />
              Showing <span className="text-white/90">{fmt(stats.shownNodes)}</span> nodes and{" "}
              <span className="text-white/90">{fmt(stats.shownEdges)}</span> links · loaded in{" "}
              <span className="text-white/90">{fmt(stats.ms)} ms</span>
            </p>
          ) : (
            <p className="mt-1 text-[12px] text-white/50">Reading the graph from FalkorDB…</p>
          )}
          <div className="mt-3 flex items-center gap-2">
            <div role="tablist" aria-label="Layer" className="flex rounded-full border border-white/10 bg-white/5 p-0.5 text-[12px]">
              {(
                [
                  ["knowledge", "Knowledge"],
                  ["full", "Everything"],
                ] as const
              ).map(([id, text]) => (
                <button
                  key={id}
                  role="tab"
                  type="button"
                  aria-selected={layer === id}
                  onClick={() => setLayer(id)}
                  className={cn(
                    "rounded-full px-3 py-1 font-medium transition-colors",
                    layer === id ? "bg-white text-[#0b1222]" : "text-white/65 hover:text-white",
                  )}
                >
                  {text}
                </button>
              ))}
            </div>
            {switching ? (
              <span className="flex items-center gap-1.5 text-[11.5px] text-white/55">
                <Loader2 className="size-3.5 animate-spin" aria-hidden /> Loading
              </span>
            ) : running ? (
              <span className="flex items-center gap-1.5 text-[11.5px] text-white/55">
                <span className="size-1.5 animate-pulse rounded-full bg-cyan-300" aria-hidden /> Arranging
              </span>
            ) : null}
          </div>
        </div>

        {/* Search */}
        <div className="pointer-events-auto relative mt-3 w-[min(340px,calc(100vw-2rem))]">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-[#0b1222]/70 px-3 shadow-[0_10px_40px_rgba(0,0,0,0.4)] backdrop-blur-md focus-within:border-white/25">
            <Search className="size-4 shrink-0 text-white/50" aria-hidden />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((a) => Math.min(a + 1, matches.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((a) => Math.max(a - 1, 0));
                } else if (e.key === "Enter" && matches[active]) {
                  pick(matches[active]);
                } else if (e.key === "Escape") {
                  setQ("");
                }
              }}
              placeholder="Find people, customers, systems, decisions"
              aria-label="Search the graph"
              className="h-10 w-full bg-transparent text-[13px] text-white placeholder:text-white/40 focus:outline-none"
            />
            {q ? (
              <button type="button" aria-label="Clear search" onClick={() => setQ("")} className="text-white/50 hover:text-white">
                <X className="size-4" />
              </button>
            ) : null}
          </div>
          {q.trim() ? (
            <ul
              role="listbox"
              className="absolute inset-x-0 top-full z-20 mt-1.5 overflow-hidden rounded-xl border border-white/10 bg-[#0b1222]/95 py-1 shadow-[0_16px_50px_rgba(0,0,0,0.55)] backdrop-blur-md"
            >
              {matches.length ? (
                matches.map((n, i) => (
                  <li key={n.id} role="option" aria-selected={i === active}>
                    <button
                      type="button"
                      onMouseEnter={() => setActive(i)}
                      onClick={() => pick(n)}
                      className={cn("flex w-full items-center gap-2.5 px-3 py-2 text-left", i === active ? "bg-white/10" : "")}
                    >
                      <span
                        className="size-2.5 shrink-0 rounded-full"
                        style={{ background: typeOf[n.type]?.color, boxShadow: `0 0 8px ${typeOf[n.type]?.color}` }}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] text-white">{n.name}</span>
                        <span className="block truncate text-[11px] text-white/45">
                          {typeOf[n.type] ? one(typeOf[n.type].label) : n.type}
                          {n.extra?.role ? ` · ${n.extra.role}` : n.extra?.plan ? ` · ${n.extra.plan}` : n.extra?.title ? ` · ${n.extra.title}` : ""}
                        </span>
                      </span>
                      <span className="shrink-0 text-[11px] tabular-nums text-white/35">{fmt(n.degree)}</span>
                    </button>
                  </li>
                ))
              ) : (
                <li className="px-3 py-2 text-[12.5px] text-white/50">
                  No match in this view.{layer === "knowledge" ? " Try Everything." : ""}
                </li>
              )}
            </ul>
          ) : null}
        </div>
      </div>

      {/* Legend */}
      {data ? (
        <div className="absolute bottom-4 left-4 max-h-[calc(100%-15rem)] w-[min(250px,calc(100vw-6rem))] md:bottom-5 md:left-5">
          <div className="flex max-h-full flex-col rounded-2xl border border-white/10 bg-[#0b1222]/70 shadow-[0_10px_40px_rgba(0,0,0,0.45)] backdrop-blur-md">
            <button
              type="button"
              onClick={() => setLegendOpen((o) => (o === null ? !window.matchMedia("(min-width: 768px)").matches : !o))}
              aria-expanded={legendOpen ?? undefined}
              className="flex items-center gap-2 px-3.5 py-2.5 text-left text-[12px] font-medium text-white/80"
            >
              <Layers className="size-3.5 text-white/50" aria-hidden />
              {data.types.length} kinds of knowledge
              <span className="ml-auto text-[11px] font-normal text-white/40">
                {legendOpen === null ? (
                  <>
                    <span className="md:hidden">Show</span>
                    <span className="hidden md:inline">Hide</span>
                  </>
                ) : legendOpen ? (
                  "Hide"
                ) : (
                  "Show"
                )}
              </span>
            </button>
            {legendOpen !== false ? (
              <div className={cn("min-h-0 overflow-y-auto px-1.5 pb-2", legendOpen === null && "hidden md:block")}>
                <ul>
                  {data.types.map((t) => {
                    const off = hidden.has(t.type);
                    return (
                      <li key={t.type}>
                        <button
                          type="button"
                          onClick={() => toggleType(t.type)}
                          aria-pressed={!off}
                          className={cn(
                            "flex w-full items-center gap-2.5 rounded-lg px-2 py-[5px] text-left text-[12px] transition-colors hover:bg-white/5",
                            off ? "text-white/30" : "text-white/85",
                          )}
                        >
                          <span
                            className="size-2.5 shrink-0 rounded-full transition-opacity"
                            style={{ background: t.color, boxShadow: off ? "none" : `0 0 10px ${t.color}`, opacity: off ? 0.25 : 1 }}
                            aria-hidden
                          />
                          <span className={cn("flex-1 truncate", off && "line-through decoration-white/20")}>{t.label}</span>
                          <span className="tabular-nums text-white/40">{fmt(t.count)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {hidden.size ? (
                  <button type="button" onClick={showAll} className="mt-1 flex items-center gap-1.5 px-2 text-[11.5px] text-cyan-200/80 hover:text-cyan-100">
                    <Eye className="size-3.5" aria-hidden /> Show all
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Zoom and layout controls */}
      <div className={cn("absolute bottom-4 flex flex-col gap-1.5 transition-[right] md:bottom-5", selected ? "right-4 md:right-[404px]" : "right-4 md:right-5")}>
        <ControlButton label="Zoom in" onClick={() => zoom("in")}>
          <Plus className="size-4" aria-hidden />
        </ControlButton>
        <ControlButton label="Zoom out" onClick={() => zoom("out")}>
          <Minus className="size-4" aria-hidden />
        </ControlButton>
        <ControlButton label="Fit to screen" onClick={() => zoom("fit")}>
          <Maximize2 className="size-4" aria-hidden />
        </ControlButton>
        <ControlButton label="Arrange again" onClick={() => runLayout(4000)} disabled={running}>
          <Play className="size-4" aria-hidden />
        </ControlButton>
      </div>

      {/* Loading and errors */}
      {!data && !error ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="flex items-center gap-2.5 rounded-full border border-white/10 bg-[#0b1222]/80 px-4 py-2 text-[13px] text-white/70 backdrop-blur-md">
            <Loader2 className="size-4 animate-spin text-cyan-300" aria-hidden /> Loading the graph from FalkorDB
          </div>
        </div>
      ) : null}
      {error ? (
        <div className="absolute inset-0 flex items-center justify-center p-6">
          <div className="max-w-sm rounded-2xl border border-white/10 bg-[#0b1222]/85 p-5 text-center backdrop-blur-md">
            <p className="text-[14px] font-medium">The graph did not load</p>
            <p className="mt-1 text-[12.5px] text-white/55">{error instanceof Error ? error.message : "Try again in a moment."}</p>
          </div>
        </div>
      ) : null}

      {/* Details panel */}
      {selected ? (
        <aside
          aria-label="Node details"
          className="absolute inset-x-3 bottom-3 top-auto max-h-[60%] overflow-hidden rounded-2xl border border-white/10 bg-[#0a1120]/85 shadow-[0_20px_60px_rgba(0,0,0,0.55)] backdrop-blur-xl md:inset-x-auto md:bottom-5 md:right-5 md:top-5 md:max-h-none md:w-[372px]"
        >
          <NodePanel
            id={selected}
            detail={detail && detail.id === selected ? detail : undefined}
            loading={detailLoading}
            color={(t) => typeOf[t]?.color ?? "#8a93a6"}
            typeLabel={(t) => (typeOf[t] ? one(typeOf[t].label) : t)}
            inView={(id) => byId.has(id)}
            fallbackName={byId.get(selected)?.name}
            onJump={(id) => select(id, true)}
            onClose={() => select(null)}
            onAsk={(question) => openAsk(question)}
          />
        </aside>
      ) : null}
    </div>
  );
}

function ControlButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      disabled={disabled}
      className="flex size-9 items-center justify-center rounded-xl border border-white/10 bg-[#0b1222]/75 text-white/75 shadow-[0_8px_30px_rgba(0,0,0,0.4)] backdrop-blur-md transition-colors hover:bg-[#16203a] hover:text-white disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function NodePanel({
  id,
  fallbackName,
  detail,
  loading,
  color,
  typeLabel,
  inView,
  onJump,
  onClose,
  onAsk,
}: {
  id: string;
  fallbackName?: string;
  detail?: NodeDetail;
  loading: boolean;
  color: (type: string) => string;
  typeLabel: (type: string) => string;
  inView: (id: string) => boolean;
  onJump: (id: string) => void;
  onClose: () => void;
  onAsk: (q: string) => void;
}) {
  const type = detail?.type ?? id.split(":")[0];
  const c = color(type);
  const text = detail ? TEXT_KEYS.map((k) => detail.props[k]).find((v) => typeof v === "string" && v.trim()) : undefined;
  const facts = detail
    ? [
        ...Object.entries(detail.props).filter(([k, v]) => !SKIP_KEYS.has(k) && v !== null && v !== "" && showValue(v).length <= 120),
        ...Object.entries(detail.aggregates ?? {}),
      ].slice(0, 12)
    : [];
  const page = detail ? pageFor(detail) : null;
  const away = (n: Neighbour) => Number(!inView(n.id));
  const groups = detail
    ? detail.neighbours
        .map((g) => ({ ...g, items: [...g.items].sort((a, b) => away(a) - away(b)) }))
        .sort((a, b) => away(a.items[0]) - away(b.items[0]))
    : [];

  return (
    <div className="flex h-full max-h-[inherit] flex-col">
      <div className="flex items-start gap-3 border-b border-white/10 px-4 py-3.5">
        <span className="mt-1.5 size-3 shrink-0 rounded-full" style={{ background: c, boxShadow: `0 0 12px ${c}` }} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em]" style={{ color: c }}>
            {typeLabel(type)}
          </p>
          <h2 className="mt-0.5 break-words text-[15px] font-semibold leading-snug text-white">{detail?.name ?? fallbackName ?? id.split(":").slice(1).join(":")}</h2>
          {detail ? <p className="mt-0.5 text-[11.5px] text-white/45">{fmt(detail.degree)} connections · read in {detail.ms} ms</p> : null}
        </div>
        <button type="button" onClick={onClose} aria-label="Close details" className="rounded-lg p-1 text-white/50 hover:bg-white/10 hover:text-white">
          <X className="size-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {!detail ? (
          <div className="space-y-2 py-2" aria-busy={loading}>
            {[80, 60, 70, 50].map((w) => (
              <div key={w} className="h-3 animate-pulse rounded bg-white/10" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : (
          <>
            {page || detail ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {page ? (
                  <Link
                    href={page.href}
                    className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-[12px] font-medium text-[#0b1222] hover:bg-white/90"
                  >
                    {page.label} <ExternalLink className="size-3.5" aria-hidden />
                  </Link>
                ) : null}
                <button
                  type="button"
                  onClick={() => onAsk(askFor(detail))}
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3 py-1.5 text-[12px] font-medium text-white/85 hover:bg-white/10"
                >
                  <MessageCircleQuestion className="size-3.5" aria-hidden /> Ask about this
                </button>
              </div>
            ) : null}

            {typeof text === "string" ? <p className="mb-3 whitespace-pre-line text-[12.5px] leading-relaxed text-white/70">{text}</p> : null}

            {facts.length ? (
              <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[12px]">
                {facts.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-white/40">{humanKey(k)}</dt>
                    <dd className="min-w-0 break-words text-white/85">{showValue(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}

            {groups.length ? (
              <div className="space-y-3.5 pb-1">
                {groups.map((g) => (
                  <section key={`${g.dir}-${g.rel}`}>
                    <h3 className="mb-1 flex items-center gap-1.5 text-[11.5px] font-medium text-white/50">
                      {g.dir === "out" ? <ArrowRight className="size-3" aria-hidden /> : <ArrowLeft className="size-3" aria-hidden />}
                      {humanRel(g.rel, g.dir)}
                      <span className="ml-auto font-normal normal-case tracking-normal text-white/35">
                        {g.total > g.items.length ? `${g.items.length} of ${fmt(g.total)}` : fmt(g.total)}
                      </span>
                    </h3>
                    <ul>
                      {g.items.map((n) => {
                        const here = inView(n.id);
                        const nc = color(n.type);
                        return (
                          <li key={n.id}>
                            <button
                              type="button"
                              disabled={!here}
                              onClick={() => onJump(n.id)}
                              title={here ? `Show ${n.name}` : "Not in this view. Switch to Everything to see it."}
                              className="group flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12.5px] enabled:hover:bg-white/[0.07] disabled:cursor-default"
                            >
                              <span className="size-2 shrink-0 rounded-full" style={{ background: nc, opacity: here ? 1 : 0.4 }} aria-hidden />
                              <span className={cn("min-w-0 flex-1 truncate", here ? "text-white/85 group-hover:text-white" : "text-white/40")}>{n.name}</span>
                              <span className="shrink-0 text-[10.5px] text-white/30">{typeLabel(n.type)}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-white/45">No connections.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
