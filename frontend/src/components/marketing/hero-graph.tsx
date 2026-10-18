"use client";

import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useEffect, useRef } from "react";

import type { LandingGraph } from "@/lib/api";
import { cn } from "@/lib/utils";

interface GNode extends SimulationNodeDatum {
  id: number;
  type: string;
  label: string;
  color: string;
  r: number;
}

interface GLink extends SimulationLinkDatum<GNode> {
  source: GNode;
  target: GNode;
}

interface Spark {
  link: GLink;
  t: number;
  speed: number;
}

/** How long each hop of a story takes to light up. */
export const STEP_MS = 420;

/** Node colours for the light landing page, by graph label. */
export const TYPE_COLOR: Record<string, string> = {
  Person: "#0a8fe6",
  Team: "#3e63dd",
  System: "#5b5bd6",
  Feature: "#12a594",
  RoadmapItem: "#46a758",
  Bug: "#e5484d",
  Ticket: "#e93d82",
  Account: "#f76b15",
  Contact: "#ffa01c",
  Promise: "#d6a10e",
  Decision: "#8e4ec6",
  Workaround: "#d6409f",
};

export const typeColor = (type: string) => TYPE_COLOR[type] ?? "#8b8d98";

const INK = "#262626";

function rgba(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function trunc(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s;
}

/**
 * The landing hero: a real slice of the company graph, laid out with d3-force and drawn on canvas.
 * `story` picks one of the agents' paths; its nodes light up hop by hop.
 */
export function HeroGraph({
  data,
  story,
  run = 0,
  className,
}: {
  data: LandingGraph | undefined;
  story: number;
  /** Changes when the same story is picked again, to replay it. */
  run?: number;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const storyRef = useRef({ index: story, at: 0 });

  useEffect(() => {
    storyRef.current = { index: story, at: performance.now() };
  }, [story, run]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---------------------------------------------------------------- graph
    const degree = new Map<number, number>();
    for (const e of data.edges) {
      degree.set(e.s, (degree.get(e.s) ?? 0) + 1);
      degree.set(e.t, (degree.get(e.t) ?? 0) + 1);
    }
    const nodes: GNode[] = data.nodes.map((n, i) => {
      const a = i * 2.39996;
      const d = Math.sqrt(i) * 2.2;
      return {
        id: n.id,
        type: n.type,
        label: n.type === "Bug" && n.key ? n.key : n.name,
        color: typeColor(n.type),
        r: Math.min(7, 2 + Math.sqrt(degree.get(n.id) ?? 0) * 0.5),
        x: Math.cos(a) * d,
        y: Math.sin(a) * d,
      };
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links: GLink[] = [];
    const between = new Map<string, GLink>();
    const neighbours = new Map<number, Set<number>>();
    for (const e of data.edges) {
      const s = byId.get(e.s);
      const t = byId.get(e.t);
      if (!s || !t) continue;
      const l = { source: s, target: t };
      links.push(l);
      between.set(`${e.s}:${e.t}`, l);
      between.set(`${e.t}:${e.s}`, l);
      if (!neighbours.has(e.s)) neighbours.set(e.s, new Set());
      if (!neighbours.has(e.t)) neighbours.set(e.t, new Set());
      neighbours.get(e.s)!.add(e.t);
      neighbours.get(e.t)!.add(e.s);
    }

    const sim = forceSimulation(nodes)
      .force(
        "link",
        forceLink<GNode, GLink>(links)
          .distance((l) => 16 + (l.source.r + l.target.r) * 2.2)
          .strength(0.16),
      )
      .force("charge", forceManyBody<GNode>().strength((n) => -24 - n.r * 6).distanceMax(340))
      .force("collide", forceCollide<GNode>((n) => n.r + 2.5))
      .force("x", forceX(0).strength(0.05))
      .force("y", forceY(0).strength(0.05))
      .alphaDecay(0.02)
      .velocityDecay(0.36)
      .stop();
    sim.tick(340);
    let gx = 0;
    let gy = 0;
    for (const n of nodes) {
      gx += n.x!;
      gy += n.y!;
    }
    gx /= nodes.length || 1;
    gy /= nodes.length || 1;
    const far = Math.max(1, ...nodes.map((n) => Math.hypot(n.x! - gx, n.y! - gy)));
    const delay = new Map(nodes.map((n) => [n.id, (Math.hypot(n.x! - gx, n.y! - gy) / far) * 700]));
    const born = performance.now();
    const BLOOM = 1300;
    // The first story starts once the graph has opened.
    storyRef.current = { ...storyRef.current, at: born + (reduced ? 0 : BLOOM + 500) };

    // ---------------------------------------------------------------- view
    let w = 0;
    let h = 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width;
      h = r.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const cam = { s: 1, cx: 0, cy: 0, sx: 0, sy: 0, px: 0, py: 0 };
    const mouse = { x: -1, y: -1, in: false };
    let angle = 0;
    let hovered: GNode | null = null;
    const screen = new Map<number, { x: number; y: number; r: number }>();

    const sparks: Spark[] = [];
    const spawn = (): Spark => ({ link: links[(Math.random() * links.length) | 0], t: 0, speed: 0.00025 + Math.random() * 0.0005 });
    if (!reduced && links.length) for (let i = 0; i < 46; i++) sparks.push({ ...spawn(), t: Math.random() });

    const target = (pathIds: number[]) => {
      const wide = w >= 1024;
      const x0 = wide ? w * 0.47 : 12;
      const x1 = wide ? w - 36 : w - 12;
      const y0 = wide ? 88 : 12;
      const y1 = wide ? h - 112 : h - 12;
      const dist = nodes.map((n) => Math.hypot(n.x! - gx, n.y! - gy) + n.r).sort((a, b) => a - b);
      const radius = Math.max(40, dist[Math.floor(dist.length * 0.97)] ?? 40);
      let s = Math.min(x1 - x0, y1 - y0) / 2 / radius;
      let cx = gx;
      let cy = gy;
      const lit = pathIds.map((id) => byId.get(id)).filter(Boolean) as GNode[];
      if (lit.length) {
        const ax = lit.reduce((a, n) => a + n.x!, 0) / lit.length;
        const ay = lit.reduce((a, n) => a + n.y!, 0) / lit.length;
        cx += (ax - gx) * (wide ? 0.35 : 0.15);
        cy += (ay - gy) * (wide ? 0.35 : 0.15);
        if (wide) s *= 1.1;
      }
      return { s, cx, cy, sx: (x0 + x1) / 2, sy: (y0 + y1) / 2 };
    };

    let opening = !reduced;
    const grown = (n: GNode, now: number) => {
      if (!opening) return 1;
      const u = Math.min(1, Math.max(0, (now - born - delay.get(n.id)!) / BLOOM));
      return 1 - Math.pow(1 - u, 3);
    };
    const project = (n: GNode, now: number) => {
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const g = grown(n, now);
      const dx = gx + (n.x! - gx) * g - cam.cx;
      const dy = gy + (n.y! - gy) * g - cam.cy;
      return { x: cam.sx + (cos * dx - sin * dy) * cam.s + cam.px, y: cam.sy + (sin * dx + cos * dy) * cam.s + cam.py };
    };

    // ---------------------------------------------------------------- draw
    // A material chip: white, hairline border, soft shadow, colour dot.
    const chip = (text: string, x: number, y: number, color: string, alpha: number, placed: DOMRect[], strong: boolean) => {
      ctx.font = `${strong ? 600 : 500} 11.5px ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`;
      const tw = ctx.measureText(text).width;
      const bw = tw + 24;
      const bh = 22;
      let bx = x + 10;
      if (bx + bw > w - 8) bx = x - 10 - bw;
      bx = Math.max(8, Math.min(bx, w - 8 - bw));
      let by = y - bh / 2;
      for (let i = 0; i < 6; i++) {
        const hit = placed.find((p) => bx < p.x + p.width && bx + bw > p.x && by < p.y + p.height && by + bh > p.y);
        if (!hit) break;
        by = hit.y + hit.height + 3;
      }
      placed.push(new DOMRect(bx, by, bw, bh));
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(15, 23, 42, 0.12)";
      ctx.shadowBlur = 8;
      ctx.shadowOffsetY = 2;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.roundRect(bx, by, bw, bh, 11);
      ctx.fill();
      ctx.shadowColor = "transparent";
      ctx.strokeStyle = strong ? rgba(color, 0.55) : "rgba(15, 23, 42, 0.09)";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(bx + 10, by + bh / 2, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = INK;
      ctx.textBaseline = "middle";
      ctx.fillText(text, bx + 17, by + bh / 2 + 0.5);
      ctx.globalAlpha = 1;
    };

    const draw = (now: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // Which nodes are lit: the hovered node and its neighbours, or the current story's path so far.
      const st = storyRef.current;
      const path = data.stories[st.index]?.path ?? [];
      const elapsed = now - st.at;
      const order = new Map<number, number>();
      if (hovered) {
        order.set(hovered.id, 0);
        let i = 1;
        for (const id of neighbours.get(hovered.id) ?? []) if (i < 40) order.set(id, i++);
      } else {
        const count = elapsed < 0 ? 0 : reduced ? path.length : Math.min(path.length, Math.floor(elapsed / STEP_MS) + 1);
        path.slice(0, count).forEach((id, i) => order.set(id, i));
      }
      const focus = order.size > 0;
      const fade = hovered ? 1 : Math.min(1, Math.max(0, elapsed) / 500);

      const t = target(elapsed < 0 ? [] : path);
      const k = reduced || now - born < 50 ? 1 : 0.045;
      cam.s += (t.s - cam.s) * k;
      cam.cx += (t.cx - cam.cx) * k;
      cam.cy += (t.cy - cam.cy) * k;
      cam.sx = t.sx;
      cam.sy = t.sy;
      if (!reduced) {
        const tx = mouse.in ? (mouse.x - w / 2) * -0.015 : 0;
        const ty = mouse.in ? (mouse.y - h / 2) * -0.015 : 0;
        cam.px += (tx - cam.px) * 0.05;
        cam.py += (ty - cam.py) * 0.05;
      }
      const zoom = Math.max(0.75, Math.min(1.4, cam.s));
      screen.clear();
      for (const n of nodes) {
        const p = project(n, now);
        screen.set(n.id, { x: p.x, y: p.y, r: n.r * zoom * (0.4 + 0.6 * grown(n, now)) });
      }
      if (opening && now - born > BLOOM + 800) opening = false;
      const shown = opening ? Math.min(1, (now - born) / BLOOM) : 1;

      // Edges: one hairline pass for everything.
      ctx.lineWidth = 0.7;
      ctx.strokeStyle = `rgba(38, 38, 38, ${shown * (focus ? 0.085 - 0.04 * fade : 0.085)})`;
      ctx.beginPath();
      for (const l of links) {
        const a = screen.get(l.source.id)!;
        const b = screen.get(l.target.id)!;
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();

      // Lit edges, coloured from the earlier hop to the later one.
      const litLinks: [GNode, GNode][] = [];
      if (focus) {
        const ids = [...order.keys()];
        for (let i = 0; i < ids.length; i++) {
          for (let j = 0; j < i; j++) {
            const l = between.get(`${ids[j]}:${ids[i]}`);
            if (l) litLinks.push(l.source.id === ids[j] ? [l.source, l.target] : [l.target, l.source]);
          }
        }
        ctx.lineWidth = 1.6;
        for (const [a, b] of litLinks) {
          const pa = screen.get(a.id)!;
          const pb = screen.get(b.id)!;
          const g = ctx.createLinearGradient(pa.x, pa.y, pb.x, pb.y);
          g.addColorStop(0, rgba(a.color, 0.7 * fade));
          g.addColorStop(1, rgba(b.color, 0.9 * fade));
          ctx.strokeStyle = g;
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
        }
      }

      // Data moving along the graph: small dots on random edges, and on the lit path.
      if (!reduced) {
        for (const s of sparks) {
          s.t += s.speed * 16;
          if (s.t >= 1) Object.assign(s, spawn());
          const a = screen.get(s.link.source.id)!;
          const b = screen.get(s.link.target.id)!;
          ctx.globalAlpha = Math.sin(Math.PI * s.t) * (focus ? 0.25 : 0.7) * shown;
          ctx.fillStyle = s.link.target.color;
          ctx.beginPath();
          ctx.arc(a.x + (b.x - a.x) * s.t, a.y + (b.y - a.y) * s.t, 1.6, 0, Math.PI * 2);
          ctx.fill();
        }
        litLinks.forEach(([a, b], i) => {
          const pa = screen.get(a.id)!;
          const pb = screen.get(b.id)!;
          const u = (((now / 1100 + i * 0.37) % 1) + 1) % 1;
          ctx.globalAlpha = fade * Math.sin(Math.PI * u);
          ctx.fillStyle = b.color;
          ctx.beginPath();
          ctx.arc(pa.x + (pb.x - pa.x) * u, pa.y + (pb.y - pa.y) * u, 2.6, 0, Math.PI * 2);
          ctx.fill();
        });
        ctx.globalAlpha = 1;
      }

      // Nodes: flat discs. Unlit nodes step back when a path is lit; lit nodes sit on a white rim.
      for (const n of nodes) {
        if (order.has(n.id)) continue;
        const p = screen.get(n.id)!;
        ctx.globalAlpha = shown * (focus ? 0.75 - 0.45 * fade : 0.75);
        ctx.fillStyle = n.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      for (const id of order.keys()) {
        const n = byId.get(id)!;
        const p = screen.get(id)!;
        ctx.shadowColor = rgba(n.color, 0.45);
        ctx.shadowBlur = 10;
        ctx.shadowOffsetY = 2;
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r + 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowColor = "transparent";
        ctx.fillStyle = n.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r + 1, 0, Math.PI * 2);
        ctx.fill();
      }

      // The newest hop pulses; the first hop sends out one ring when a story starts.
      if (focus && !reduced) {
        const ids = [...order.keys()];
        const last = byId.get(ids[ids.length - 1])!;
        const head = screen.get(last.id)!;
        const pulse = (now % 1200) / 1200;
        ctx.strokeStyle = rgba(last.color, 0.6 * (1 - pulse));
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(head.x, head.y, head.r + 5 + pulse * 16, 0, Math.PI * 2);
        ctx.stroke();
        if (!hovered && elapsed < 1400) {
          const first = byId.get(ids[0])!;
          const p = screen.get(first.id)!;
          const u = elapsed / 1400;
          ctx.strokeStyle = rgba(first.color, 0.35 * (1 - u));
          ctx.beginPath();
          ctx.arc(p.x, p.y, 8 + u * 140, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // Labels for lit nodes, faded in hop by hop.
      const placed: DOMRect[] = [];
      for (const [id, i] of order) {
        if (hovered && i > 8) continue;
        const n = byId.get(id)!;
        const p = screen.get(id)!;
        const a = hovered || reduced ? 1 : Math.min(1, Math.max(0, (elapsed - i * STEP_MS) / 260));
        chip(trunc(n.label, 34), p.x + p.r, p.y, n.color, a, placed, i === 0);
      }
    };

    // ---------------------------------------------------------------- loop
    let raf = 0;
    let visible = true;
    let last = performance.now();
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(50, now - last);
      last = now;
      if (!reduced) angle += dt * 0.00003;
      draw(now);
    };
    const start = () => {
      if (!raf && visible) {
        last = performance.now();
        raf = requestAnimationFrame(frame);
      }
    };
    const stop = () => {
      cancelAnimationFrame(raf);
      raf = 0;
    };
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible) start();
      else stop();
    });
    io.observe(canvas);
    start();

    const onMove = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      mouse.x = e.clientX - r.left;
      mouse.y = e.clientY - r.top;
      mouse.in = mouse.x >= 0 && mouse.y >= 0 && mouse.x <= r.width && mouse.y <= r.height;
      let best: GNode | null = null;
      let bestD = e.target === canvas ? 14 : -Infinity;
      for (const n of nodes) {
        const p = screen.get(n.id);
        if (!p) continue;
        const d = Math.hypot(p.x - mouse.x, p.y - mouse.y) - p.r;
        if (d < bestD) {
          bestD = d;
          best = n;
        }
      }
      if (best !== hovered) {
        hovered = best;
        canvas.style.cursor = best ? "pointer" : "";
        if (!best) storyRef.current = { ...storyRef.current, at: performance.now() - 10 * STEP_MS };
      }
    };
    const onLeave = () => {
      mouse.in = false;
      if (hovered) storyRef.current = { ...storyRef.current, at: performance.now() - 10 * STEP_MS };
      hovered = null;
      canvas.style.cursor = "";
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    canvas.addEventListener("pointerleave", onLeave);

    return () => {
      stop();
      io.disconnect();
      ro.disconnect();
      sim.stop();
      window.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, [data]);

  return <canvas ref={canvasRef} className={cn("block h-full w-full", className)} aria-hidden />;
}
