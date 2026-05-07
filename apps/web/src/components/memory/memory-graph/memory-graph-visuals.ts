import type { MemoryGraphEdge, MemoryGraphNode, MemoryLearningNode } from "@/lib/types";

export type MemoryNode = MemoryGraphNode | MemoryLearningNode;

export type NodeInteractionState = "idle" | "hovered" | "selected" | "neighbor" | "dimmed";
export type EdgeInteractionState = "idle" | "active" | "dimmed";

export interface Vec2 {
  x: number;
  y: number;
}

export function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

export function seededUnit(value: string): number {
  return (hashString(value) % 10_000) / 10_000;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function getNodeRadius(degree: number): number {
  return 6 + Math.sqrt(Math.max(1, degree)) * 2.6;
}

export function computeDegree(edges: MemoryGraphEdge[]): Map<string, number> {
  const degree = new Map<string, number>();
  edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  });
  return degree;
}

export interface NodeStyle {
  fill: string;
  stroke: string | null;
  strokeWidth: number;
  opacity: number;
}

const NODE_FILL_IDLE = "rgba(220, 220, 220, 0.95)";
const NODE_FILL_ACCENT = "var(--accent)";
const NODE_STROKE_IDLE = "rgba(0, 0, 0, 0.85)";
const NODE_STROKE_ACCENT = "var(--accent)";

export function getNodeStyle(_node: MemoryNode, state: NodeInteractionState): NodeStyle {
  if (state === "selected") {
    return {
      fill: NODE_FILL_ACCENT,
      stroke: NODE_STROKE_ACCENT,
      strokeWidth: 2,
      opacity: 1,
    };
  }
  if (state === "hovered") {
    return {
      fill: NODE_FILL_ACCENT,
      stroke: NODE_STROKE_ACCENT,
      strokeWidth: 1.5,
      opacity: 1,
    };
  }
  if (state === "neighbor") {
    return {
      fill: NODE_FILL_ACCENT,
      stroke: NODE_STROKE_ACCENT,
      strokeWidth: 1,
      opacity: 1,
    };
  }
  if (state === "dimmed") {
    return { fill: NODE_FILL_IDLE, stroke: NODE_STROKE_IDLE, strokeWidth: 1, opacity: 0.12 };
  }
  return { fill: NODE_FILL_IDLE, stroke: NODE_STROKE_IDLE, strokeWidth: 1, opacity: 1 };
}

export interface EdgeStyle {
  stroke: string;
  opacity: number;
  width: number;
}

const EDGE_STROKE_IDLE = "rgba(180, 180, 180, 1)";
const EDGE_STROKE_ACTIVE = "var(--accent)";

export function getEdgeStyle(_edge: MemoryGraphEdge, state: EdgeInteractionState): EdgeStyle {
  if (state === "active") {
    return { stroke: EDGE_STROKE_ACTIVE, opacity: 0.85, width: 1.5 };
  }
  if (state === "dimmed") {
    return { stroke: EDGE_STROKE_IDLE, opacity: 0.04, width: 1 };
  }
  return { stroke: EDGE_STROKE_IDLE, opacity: 0.18, width: 1 };
}
