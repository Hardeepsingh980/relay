"use client";

import { useEffect, useMemo, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition, type StylesheetJson } from "cytoscape";

import type { GraphView } from "@/lib/types";
import { cn } from "@/lib/utils";

type Variant = "handover" | "dayone";

interface Props {
  graph: GraphView;
  centerId: string;
  departed?: boolean;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  variant?: Variant;
  className?: string;
  label: string;
}

function cssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** Concentric rings: what depends on the centre alone sits closest to it. */
function levelOf(n: GraphView["nodes"][number], variant: Variant) {
  if (variant === "dayone") return n.kind === "person" ? 0 : n.kind === "decision" ? 1 : 2;
  if (n.kind === "person") return 0;
  return n.risk === "unique" ? 2 : 1;
}

function shorten(s: string, n = 26) {
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}


export function KnowledgeGraph({ graph, centerId, departed = false, selectedId, onSelect, variant = "handover", className, label }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  const key = useMemo(() => graph.nodes.map((n) => n.id).sort().join("|") + "#" + graph.edges.length, [graph]);

  // Build once per distinct graph shape; state changes are applied as classes below.
  useEffect(() => {
    if (!ref.current) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const c = {
      card: cssVar("--card", "#ffffff"),
      fg: cssVar("--foreground", "#1c1917"),
      muted: cssVar("--muted-foreground", "#78716c"),
      border: cssVar("--border", "#e7e5e4"),
      brand: cssVar("--brand", "#4f46e5"),
      risk: cssVar("--risk-high", "#dc2626"),
      riskSoft: cssVar("--risk-high-soft", "#fef2f2"),
      warn: cssVar("--risk-medium", "#d97706"),
      warnSoft: cssVar("--risk-medium-soft", "#fffbeb"),
      covered: cssVar("--covered", "#16a34a"),
      coveredSoft: cssVar("--covered-soft", "#f0fdf4"),
      secondary: cssVar("--secondary", "#f5f5f4"),
    };
    const ids = new Set(graph.nodes.map((n) => n.id));
    const elements: ElementDefinition[] = [
      ...graph.nodes.map((n) => ({
        data: {
          id: n.id,
          label: shorten(n.name, n.kind === "person" ? 20 : 24),
          full: n.name,
          kind: n.kind,
          center: n.id === centerId ? 1 : 0,
          level: n.id === centerId ? 3 : levelOf(n, variant),
        },
        classes: [n.kind, variant, n.id === centerId ? "center" : "", n.risk ? `risk-${n.risk}` : "", n.state ? `state-${n.state}` : ""]
          .filter(Boolean)
          .join(" "),
      })),
      ...graph.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target) && (variant === "dayone" || e.type !== "ABOUT"))
        .map((e, i) => ({
          data: { id: `e${i}-${e.source}-${e.target}-${e.type}`, source: e.source, target: e.target, type: e.type, score: e.score ?? 0.3 },
          classes: [e.source === centerId ? "from-center" : "", e.type === "ABOUT" ? "about" : "", e.handover ? "handover" : "", e.type === "VERIFIED" ? "verified" : ""]
            .filter(Boolean)
            .join(" "),
        })),
    ];
    const style: StylesheetJson = [
      {
        selector: "node",
        style: {
          "background-color": c.card,
          "border-width": 1.5,
          "border-color": c.muted,
          width: 24,
          height: 24,
          label: "data(label)",
          "font-size": 10.5,
          "font-family": "Geist, ui-sans-serif, system-ui, sans-serif",
          color: c.muted,
          "text-valign": "bottom",
          "text-margin-y": 5,
          "text-wrap": "none",
          "text-background-color": c.card,
          "text-background-opacity": 0.85,
          "text-background-padding": "1px",
          "text-background-shape": "roundrectangle",
          "transition-property": "background-color, border-color, opacity, border-width, color",
          "transition-duration": reduce ? 0 : 300,
          "transition-timing-function": "ease-out",
        },
      },
      { selector: "node.person", style: { shape: "ellipse", width: 20, height: 20, "background-color": c.secondary } },
      { selector: "node.system", style: { shape: "round-rectangle" } },
      { selector: "node.customer", style: { shape: "round-hexagon", width: 24, height: 24 } },
      { selector: "node.decision", style: { shape: "diamond", width: 24, height: 24 } },
      { selector: "node.workaround", style: { shape: "round-triangle", width: 24, height: 22 } },
      { selector: "node.center", style: { width: 34, height: 34, "border-width": 2, "border-color": c.fg, "background-color": c.secondary, color: c.fg, "font-size": 11, "font-weight": 600 } },
      { selector: "node.state-verified", style: { "border-color": c.covered, "background-color": c.coveredSoft } },
      { selector: "node.state-dismissed", style: { opacity: 0.45 } },
      {
        selector: "edge",
        style: {
          width: "mapData(score, 0, 1, 0.6, 2.2)",
          "line-color": c.border,
          "curve-style": "bezier",
          "target-arrow-shape": "none",
          opacity: 0.9,
          "transition-property": "opacity, line-color, width",
          "transition-duration": reduce ? 0 : 300,
        },
      },
      { selector: "edge.about", style: { "line-style": "dotted", width: 1, opacity: 0.7 } },
      { selector: "edge.handover", style: { "line-style": "dashed", "line-color": c.brand, opacity: 0.6 } },
      { selector: "edge.verified", style: { "line-style": "solid", "line-color": c.covered, opacity: 0.9 } },
      // departure state (element classes; cytoscape can't see DOM classes)
      { selector: "node.center.departed", style: { opacity: 0.22, "border-style": "dashed" } },
      { selector: "edge.from-center.departed", style: { opacity: 0.12, "line-style": "dashed" } },
      { selector: "node.risk-unique.departed", style: { "border-color": c.risk, "background-color": c.riskSoft, "border-width": 2, color: c.risk } },
      { selector: "node.risk-thin.departed", style: { "border-color": c.warn, "background-color": c.warnSoft, "border-width": 2 } },
      { selector: "node.risk-unique.state-verified.departed", style: { "border-color": c.covered, "background-color": c.coveredSoft, color: c.covered } },
      { selector: "node.risk-unique.state-dismissed.departed", style: { "border-color": c.muted, "background-color": c.card, color: c.muted, opacity: 0.5 } },
      // day one: what you inherit is marked by coverage, no toggle needed
      { selector: "node.dayone.risk-unique", style: { "border-color": c.risk, "background-color": c.riskSoft } },
      { selector: "node.dayone.risk-covered", style: { "border-color": c.covered, "background-color": c.coveredSoft } },
      { selector: "node:selected, node.selected", style: { "border-color": c.brand, "border-width": 3, color: c.fg } },
      { selector: "node.faded", style: { opacity: 0.35 } },
    ];
    const cy = cytoscape({
      container: ref.current,
      elements,
      style,
      layout: {
        name: "concentric",
        concentric: (n: cytoscape.NodeSingular) => n.data("level"),
        levelWidth: () => 1,
        minNodeSpacing: variant === "dayone" ? 30 : 34,
        spacingFactor: 1,
        avoidOverlap: true,
        startAngle: (3 / 2) * Math.PI,
        animate: false,
        padding: 24,
      } as cytoscape.LayoutOptions,
      minZoom: 0.4,
      maxZoom: 2.2,
      wheelSensitivity: 0.2,
      boxSelectionEnabled: false,
      autounselectify: true,
    });
    cy.on("tap", "node", (evt) => onSelectRef.current?.(evt.target.id()));
    cy.on("tap", (evt) => {
      if (evt.target === cy) onSelectRef.current?.(null);
    });
    cy.on("mouseover", "node", (evt) => {
      evt.target.data("label", evt.target.data("full"));
      if (ref.current) ref.current.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", (evt) => {
      const n = evt.target;
      n.data("label", shorten(n.data("full"), n.hasClass("person") ? 20 : 24));
      if (ref.current) ref.current.style.cursor = "default";
    });
    cy.fit(undefined, 28);
    cyRef.current = cy;
    const ro = new ResizeObserver(() => {
      cy.resize();
      cy.fit(undefined, 28);
    });
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, centerId, variant]);

  // Apply state changes (risk state, departure, selection) without rebuilding.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    for (const n of graph.nodes) {
      const el = cy.getElementById(n.id);
      if (!el.nonempty()) continue;
      el.removeClass("state-at_risk state-assigned state-captured state-verified state-dismissed state-blocked risk-unique risk-shared risk-thin risk-covered");
      if (n.state) el.addClass(`state-${n.state}`);
      if (n.risk) el.addClass(`risk-${n.risk}`);
    }
  }, [graph]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().toggleClass("departed", departed);
    });
  }, [departed, key]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().removeClass("selected faded");
      if (selectedId) {
        const sel = cy.getElementById(selectedId);
        if (sel.nonempty()) {
          sel.addClass("selected");
          const keep = sel.closedNeighborhood().nodes();
          cy.nodes().difference(keep).addClass("faded");
        }
      }
    });
  }, [selectedId, key]);

  return (
    <div className={cn("relative", className)}>
      <div ref={ref} role="img" aria-label={label} className="h-full w-full" />
    </div>
  );
}

export function GraphLegend({ showRisk = true }: { showRisk?: boolean }) {
  const item = (shape: React.ReactNode, text: string) => (
    <span className="inline-flex items-center gap-1.5">
      {shape}
      {text}
    </span>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      {item(<span className="size-2.5 rounded-full border border-muted-foreground bg-secondary" />, "Person")}
      {item(<span className="size-2.5 rounded-[2px] border border-muted-foreground" />, "System")}
      {item(<span className="size-2.5 rotate-45 border border-muted-foreground" />, "Decision")}
      {item(<span className="size-0 border-x-[5px] border-b-[9px] border-x-transparent border-b-muted-foreground" />, "Workaround")}
      {showRisk ? (
        <>
          {item(<span className="size-2.5 rounded-full border-2 border-risk bg-risk-soft" />, "Only one person knows")}
          {item(<span className="size-2.5 rounded-full border-2 border-warn bg-warn-soft" />, "Only one other knows")}
          {item(<span className="size-2.5 rounded-full border-2 border-covered bg-covered-soft" />, "Handed over")}
        </>
      ) : null}
    </div>
  );
}

export function RelationshipList({ items }: { items: string[] }) {
  return (
    <details className="mt-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none hover:text-foreground">Show relationships as text</summary>
      <ul className="mt-2 max-h-48 list-disc space-y-0.5 overflow-auto pl-5">
        {items.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
    </details>
  );
}
