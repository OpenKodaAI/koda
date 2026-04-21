import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { MemoryGraphEdge } from "@/lib/types";
import {
  computeDegree,
  getNodeRadius,
  hashString,
  type MemoryNode,
} from "./memory-graph-visuals";

export interface SimNode extends SimulationNodeDatum {
  id: string;
  node: MemoryNode;
  radius: number;
  degree: number;
}

export interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string;
  edge: MemoryGraphEdge;
  weight: number;
}

export interface SimulationBundle {
  simulation: Simulation<SimNode>;
  simNodes: SimNode[];
  simLinks: SimLink[];
}

export interface CreateSimulationOptions {
  nodes: MemoryNode[];
  edges: MemoryGraphEdge[];
  width: number;
  height: number;
  previous?: SimulationBundle | null;
  reducedMotion?: boolean;
}

function initialPosition(id: string, width: number, height: number): { x: number; y: number } {
  const h = hashString(id);
  // Scatter seed around center within ±radius range.
  const ax = ((h & 0xffff) / 0xffff - 0.5) * Math.min(width, height) * 0.6;
  const ay = (((h >>> 16) & 0xffff) / 0xffff - 0.5) * Math.min(width, height) * 0.6;
  return { x: width / 2 + ax, y: height / 2 + ay };
}

export function createSimulation(options: CreateSimulationOptions): SimulationBundle {
  const { nodes, edges, width, height, previous, reducedMotion = false } = options;

  const degreeMap = computeDegree(edges);
  const previousSimNodes = new Map<string, SimNode>();
  if (previous) {
    previous.simNodes.forEach((simNode) => previousSimNodes.set(simNode.id, simNode));
  }

  const simNodes: SimNode[] = nodes.map((node) => {
    const degree = degreeMap.get(node.id) ?? 0;
    const existing = previousSimNodes.get(node.id);
    const seed = initialPosition(node.id, width, height);
    return {
      id: node.id,
      node,
      degree,
      radius: getNodeRadius(degree),
      x: existing?.x ?? seed.x,
      y: existing?.y ?? seed.y,
      vx: existing?.vx ?? 0,
      vy: existing?.vy ?? 0,
    };
  });

  const idIndex = new Map(simNodes.map((simNode) => [simNode.id, simNode]));

  const simLinks: SimLink[] = [];
  edges.forEach((edge) => {
    const source = idIndex.get(edge.source);
    const target = idIndex.get(edge.target);
    if (!source || !target) return;
    const weight = edge.weight ?? edge.similarity ?? 0.4;
    simLinks.push({
      id: edge.id,
      edge,
      source,
      target,
      weight,
    });
  });

  const simulation = forceSimulation<SimNode>(simNodes)
    .force(
      "link",
      forceLink<SimNode, SimLink>(simLinks)
        .id((node) => node.id)
        .distance(90)
        .strength(0.45),
    )
    .force("charge", forceManyBody<SimNode>().strength(-180).distanceMax(450))
    .force("collide", forceCollide<SimNode>().radius((d) => d.radius + 8).strength(0.9))
    .force("center", forceCenter(width / 2, height / 2).strength(0.06))
    .velocityDecay(0.4);

  if (reducedMotion) {
    simulation.alpha(1).alphaDecay(0.035);
    simulation.tick(300);
    simulation.alpha(0).alphaTarget(0).stop();
  } else {
    simulation.alpha(1).alphaDecay(0.035);
    simulation.tick(150);
    simulation.alphaTarget(0.02).alphaDecay(0).restart();
  }

  return { simulation, simNodes, simLinks };
}
