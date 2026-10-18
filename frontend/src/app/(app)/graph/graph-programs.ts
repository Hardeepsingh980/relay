// WebGL and canvas drawing for the knowledge graph. Browser only: import it dynamically.

import type { Attributes } from "graphology-types";
import { NodeCircleProgram } from "sigma/rendering";
import type { Settings } from "sigma/settings";
import type { NodeDisplayData, PartialButFor } from "sigma/types";

// How far the halo reaches, as a multiple of the node radius.
const GLOW = "2.7";

// language=GLSL
const VERTEX = /* glsl */ `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_position;
attribute float a_size;
attribute float a_angle;

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_correctionRatio;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

const float bias = 255.0 / 254.0;

void main() {
  float radius = a_size * u_correctionRatio / u_sizeRatio * 2.0;
  #ifdef PICKING_MODE
  float reach = radius;
  #else
  float reach = radius * ${GLOW};
  #endif
  // An equilateral triangle whose inscribed circle has radius "reach".
  vec2 diffVector = reach * 2.0 * vec2(cos(a_angle), sin(a_angle));
  gl_Position = vec4((u_matrix * vec3(a_position + diffVector, 1)).xy, 0, 1);
  v_diffVector = diffVector;
  v_radius = radius;
  #ifdef PICKING_MODE
  v_color = a_id;
  #else
  v_color = a_color;
  #endif
  v_color.a *= bias;
}
`;

// A solid core with a hot centre and a soft halo. Output is premultiplied (sigma blends ONE, ONE_MINUS_SRC_ALPHA).
// language=GLSL
const FRAGMENT = /* glsl */ `
precision highp float;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

uniform float u_correctionRatio;

void main(void) {
  float d = length(v_diffVector);
  #ifdef PICKING_MODE
  gl_FragColor = d > v_radius ? vec4(0.0) : v_color;
  #else
  float aa = u_correctionRatio * 1.6;
  float core = 1.0 - smoothstep(v_radius - aa, v_radius, d);
  float g = clamp(1.0 - (d - v_radius) / (v_radius * (${GLOW} - 1.0)), 0.0, 1.0);
  float halo = g * g * g * 0.5;
  float centre = clamp(1.0 - d / v_radius, 0.0, 1.0);
  vec3 rgb = mix(v_color.rgb, vec3(1.0), 0.5 * centre * centre);
  float a = max(core, halo) * v_color.a;
  gl_FragColor = vec4(rgb * a, a);
  #endif
}
`;

export class GlowNodeProgram extends NodeCircleProgram {
  getDefinition() {
    return { ...super.getDefinition(), VERTEX_SHADER_SOURCE: VERTEX, FRAGMENT_SHADER_SOURCE: FRAGMENT };
  }
}

type LabelData = PartialButFor<NodeDisplayData, "x" | "y" | "size" | "label" | "color"> & { typeLabel?: string };

/** Light label beside the node, with a dark shadow so it reads over edges. */
export function drawLabel<N extends Attributes, E extends Attributes, G extends Attributes>(
  ctx: CanvasRenderingContext2D,
  data: LabelData,
  settings: Settings<N, E, G>,
) {
  if (!data.label) return;
  const big = data.size >= 11;
  const size = big ? 13 : 11.5;
  ctx.font = `${big ? 600 : 500} ${size}px ${settings.labelFont}`;
  ctx.fillStyle = big ? "rgba(240, 246, 255, 0.96)" : "rgba(196, 210, 238, 0.85)";
  ctx.shadowColor = "rgba(2, 6, 16, 0.95)";
  ctx.shadowBlur = 6;
  ctx.fillText(data.label, data.x + data.size + 5, data.y + size / 3);
  ctx.shadowBlur = 0;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** Hovered or selected node: a ring and a dark glass tag with the name and type. */
export function drawHover<N extends Attributes, E extends Attributes, G extends Attributes>(
  ctx: CanvasRenderingContext2D,
  data: LabelData,
  settings: Settings<N, E, G>,
) {
  const color = data.color.startsWith("rgba") ? data.color.replace(/,\s*[\d.]+\)$/, ", 1)") : data.color;
  ctx.beginPath();
  ctx.arc(data.x, data.y, data.size + 4, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.9;
  ctx.stroke();
  ctx.globalAlpha = 1;
  if (!data.label) return;

  const font = settings.labelFont;
  const title = data.label;
  const sub = data.typeLabel ?? "";
  ctx.font = `600 13px ${font}`;
  const tw = ctx.measureText(title).width;
  ctx.font = `500 10.5px ${font}`;
  const sw = sub ? ctx.measureText(sub.toUpperCase()).width : 0;
  const padX = 10;
  const h = sub ? 40 : 26;
  const w = Math.max(tw, sw) + padX * 2;
  const x = data.x + data.size + 9;
  const y = data.y - h / 2;

  ctx.shadowColor = "rgba(0, 0, 0, 0.55)";
  ctx.shadowBlur = 16;
  roundRect(ctx, x, y, w, h, 9);
  ctx.fillStyle = "rgba(9, 14, 28, 0.92)";
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = "rgba(246, 249, 255, 1)";
  ctx.font = `600 13px ${font}`;
  ctx.fillText(title, x + padX, y + (sub ? 17 : 17));
  if (sub) {
    ctx.fillStyle = color;
    ctx.font = `500 10.5px ${font}`;
    ctx.fillText(sub.toUpperCase(), x + padX, y + 32);
  }
}
