"use client";

import { useEffect, useRef } from "react";
import cytoscape, { type Core, type StylesheetJson } from "cytoscape";

import type { CaseEdge, CaseNode } from "@/lib/relay";
import { cn } from "@/lib/utils";

function cssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function shorten(s: string, n = 26) {
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

const SHAPE: Record<string, string> = {
  account: "round-hexagon",
  contact: "ellipse",
  person: "ellipse",
  ticket: "round-rectangle",
  bug: "diamond",
  feature: "round-rectangle",
  usage: "round-tag",
  conversation: "round-rectangle",
  signal: "round-triangle",
  invoice: "round-rectangle",
  promise: "round-pentagon",
  roadmap: "round-rectangle",
  meeting: "round-rectangle",
  episode: "ellipse",
  playbook: "round-rectangle",
  system: "round-rectangle",
  action: "star",
};

interface Props {
  nodes: CaseNode[];
  edges: CaseEdge[];
  causal: { nodeIds: string[]; edgeIds: string[] };
  focus?: string[] | null;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  className?: string;
}

/** The investigation's case graph: grows as tools return, then lights up the causal chain. */
export function CaseGraph({ nodes, edges, causal, focus, selectedId, onSelect, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelect);
  const layoutTimer = useRef<number | null>(null);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!ref.current) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const c = {
      card: cssVar("--card", "#fff"),
      fg: cssVar("--foreground", "#262626"),
      muted: cssVar("--muted-foreground", "#757577"),
      border: cssVar("--border", "#ebebec"),
      brand: cssVar("--brand", "#008ae8"),
      brandSoft: cssVar("--brand-soft", "#e0f2fe"),
      risk: cssVar("--risk-high", "#d93036"),
      riskSoft: cssVar("--risk-high-soft", "#fdecec"),
      warn: cssVar("--risk-medium", "#c26a00"),
      warnSoft: cssVar("--risk-medium-soft", "#fff4d6"),
      covered: cssVar("--covered", "#15964a"),
      coveredSoft: cssVar("--covered-soft", "#e3f6ea"),
      secondary: cssVar("--secondary", "#f2f2f3"),
    };
    const style: StylesheetJson = [
      {
        selector: "node",
        style: {
          "background-color": c.card,
          "border-width": 1.5,
          "border-color": c.muted,
          width: 22,
          height: 22,
          shape: "data(shape)" as unknown as "ellipse",
          label: "data(label)",
          "font-size": 10,
          "font-family": "ui-sans-serif, system-ui, sans-serif",
          color: c.muted,
          "text-valign": "bottom",
          "text-margin-y": 5,
          "text-background-color": c.card,
          "text-background-opacity": 0.85,
          "text-background-padding": "1px",
          "text-background-shape": "roundrectangle",
          "transition-property": "background-color, border-color, opacity, border-width, width, height",
          "transition-duration": reduce ? 0 : 350,
        },
      },
      { selector: "node.account", style: { width: 34, height: 34, "border-width": 2, "border-color": c.fg, "background-color": c.secondary, color: c.fg, "font-weight": 600, "font-size": 11 } },
      { selector: "node.account.affected", style: { width: 26, height: 26, "border-color": c.warn, "background-color": c.warnSoft, "font-weight": 500 } },
      { selector: "node.bug", style: { width: 28, height: 28, "border-color": c.risk, "background-color": c.riskSoft, color: c.risk } },
      { selector: "node.status-former", style: { "border-style": "dashed", opacity: 0.75 } },
      { selector: "node.status-leaving", style: { "border-color": c.warn, "background-color": c.warnSoft } },
      { selector: "node.signal.status-risk", style: { "border-color": c.risk, "background-color": c.riskSoft } },
      { selector: "node.signal.status-positive", style: { "border-color": c.covered, "background-color": c.coveredSoft } },
      { selector: "node.usage.status-declining", style: { "border-color": c.risk, "background-color": c.riskSoft } },
      { selector: "node.promise.status-at_risk", style: { "border-color": c.warn, "background-color": c.warnSoft } },
      { selector: "node.invoice.status-late", style: { "border-color": c.warn, "background-color": c.warnSoft } },
      { selector: "node.action", style: { "border-color": c.covered, "background-color": c.coveredSoft, width: 24, height: 24 } },
      { selector: "node.fresh", style: { "border-width": 3, "border-color": c.brand } },
      { selector: "node.causal", style: { "border-color": c.risk, "border-width": 2.5, color: c.fg } },
      { selector: "node.dim", style: { opacity: 0.25 } },
      { selector: "node.selected", style: { "border-color": c.brand, "border-width": 3, color: c.fg } },
      {
        selector: "edge",
        style: {
          width: 1.2,
          "line-color": c.border,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "target-arrow-color": c.border,
          "arrow-scale": 0.7,
          label: "",
          "font-size": 8,
          color: c.muted,
          "transition-property": "line-color, width, opacity",
          "transition-duration": reduce ? 0 : 350,
        },
      },
      { selector: "edge.possible", style: { "line-style": "dashed" } },
      { selector: "edge.causal", style: { width: 2.6, "line-color": c.risk, "target-arrow-color": c.risk, label: "data(label)", "text-rotation": "autorotate", "text-background-color": c.card, "text-background-opacity": 0.9 } },
      { selector: "edge.dim", style: { opacity: 0.2 } },
    ];
    const cy = cytoscape({
      container: ref.current,
      style,
      minZoom: 0.3,
      maxZoom: 2.4,
      wheelSensitivity: 0.2,
      boxSelectionEnabled: false,
      autounselectify: true,
    });
    cy.on("tap", "node", (e) => onSelectRef.current?.(e.target.id()));
    cy.on("tap", (e) => {
      if (e.target === cy) onSelectRef.current?.(null);
    });
    cy.on("mouseover", "node", (e) => {
      e.target.data("label", e.target.data("full"));
      if (ref.current) ref.current.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", (e) => {
      e.target.data("label", shorten(e.target.data("full")));
      if (ref.current) ref.current.style.cursor = "default";
    });
    cyRef.current = cy;
    const ro = new ResizeObserver(() => {
      cy.resize();
      cy.fit(undefined, 30);
    });
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  // Add new nodes and edges as they stream in, then re-run the layout (debounced).
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    let added = 0;
    cy.batch(() => {
      for (const n of nodes) {
        if (cy.getElementById(n.id).nonempty()) continue;
        const anchor = cy.getElementById(nodes[0]?.id ?? "");
        const pos = anchor.nonempty() ? anchor.position() : { x: 0, y: 0 };
        cy.add({
          group: "nodes",
          data: { id: n.id, label: shorten(n.label), full: n.label, shape: SHAPE[n.kind] ?? "ellipse" },
          position: { x: pos.x + (Math.random() - 0.5) * 60, y: pos.y + (Math.random() - 0.5) * 60 },
          classes: [n.kind, n.status ? `status-${n.status}` : "", n.role === "affected" ? "affected" : "", "fresh"].join(" "),
        });
        added++;
        const id = n.id;
        window.setTimeout(() => cy.getElementById(id).removeClass("fresh"), 900);
      }
      for (const e of edges) {
        if (cy.getElementById(e.id).nonempty()) continue;
        if (cy.getElementById(e.source).empty() || cy.getElementById(e.target).empty()) continue;
        cy.add({ group: "edges", data: { id: e.id, source: e.source, target: e.target, label: e.label }, classes: e.possible ? "possible" : "" });
        added++;
      }
    });
    if (!added) return;
    if (layoutTimer.current) window.clearTimeout(layoutTimer.current);
    layoutTimer.current = window.setTimeout(() => {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      cy.layout({
        name: "cose",
        animate: !reduce,
        animationDuration: 500,
        fit: true,
        padding: 30,
        nodeRepulsion: () => 9000,
        idealEdgeLength: () => 70,
        gravity: 0.6,
        numIter: 800,
        randomize: false,
      } as cytoscape.LayoutOptions).run();
    }, 120);
  }, [nodes, edges]);

  // Causal chain and focus.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass("causal dim");
      const keep = new Set(focus?.length ? focus : causal.nodeIds);
      if (causal.nodeIds.length) {
        for (const id of causal.nodeIds) cy.getElementById(id).addClass("causal");
        for (const id of causal.edgeIds) cy.getElementById(id).addClass("causal");
      }
      if (focus?.length) {
        cy.nodes().forEach((n) => {
          if (!keep.has(n.id())) n.addClass("dim");
        });
      }
    });
  }, [causal, focus, nodes.length]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("selected");
    if (selectedId) cy.getElementById(selectedId).addClass("selected");
  }, [selectedId]);

  return (
    <div className={cn("relative", className)}>
      <div ref={ref} role="img" aria-label={`Investigation graph with ${nodes.length} items and ${edges.length} links`} className="absolute inset-0 h-full w-full" />
    </div>
  );
}

export function CaseLegend() {
  const dot = (cls: string, text: string) => (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2.5 border", cls)} />
      {text}
    </span>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      {dot("rounded-full border-foreground bg-secondary", "Account")}
      {dot("rounded-full border-muted-foreground", "Person")}
      {dot("rotate-45 border-risk bg-risk-soft", "Bug")}
      {dot("rounded-[2px] border-muted-foreground", "Ticket / feature")}
      {dot("rounded-full border-risk bg-risk-soft", "Warning sign")}
      {dot("rounded-full border-warn bg-warn-soft", "Promise / person leaving")}
      <span className="inline-flex items-center gap-1.5">
        <span className="h-0.5 w-4 bg-risk" /> How it connects
      </span>
    </div>
  );
}
