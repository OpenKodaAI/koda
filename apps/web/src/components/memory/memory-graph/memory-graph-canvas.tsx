"use client";

import { Minus, Plus, RotateCcw } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { MemoryGraphEdge } from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  createSimulation,
  type SimNode,
  type SimulationBundle,
} from "./memory-graph-simulation";
import {
  getEdgeStyle,
  getNodeStyle,
  type EdgeInteractionState,
  type MemoryNode,
  type NodeInteractionState,
} from "./memory-graph-visuals";
import {
  useMemoryGraphInteraction,
  type GraphBounds,
} from "./use-memory-graph-interaction";

interface MemoryGraphCanvasProps {
  nodes: MemoryNode[];
  edges: MemoryGraphEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onRequestSearchFocus?: () => void;
}

function buildNeighbors(edges: MemoryGraphEdge[], focusId: string | null) {
  const neighbors = new Set<string>();
  const edgeIds = new Set<string>();
  if (!focusId) return { neighbors, edgeIds };
  neighbors.add(focusId);
  edges.forEach((edge) => {
    if (edge.source === focusId) {
      neighbors.add(edge.target);
      edgeIds.add(edge.id);
    } else if (edge.target === focusId) {
      neighbors.add(edge.source);
      edgeIds.add(edge.id);
    }
  });
  return { neighbors, edgeIds };
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    mql.addEventListener?.("change", listener);
    return () => mql.removeEventListener?.("change", listener);
  }, []);
  return reduced;
}

export function MemoryGraphCanvas({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  onRequestSearchFocus,
}: MemoryGraphCanvasProps) {
  const { t } = useAppI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const worldGroupRef = useRef<SVGGElement | null>(null);
  const nodeGroupsRef = useRef(new Map<string, SVGGElement | null>());
  const lineRefsRef = useRef(new Map<string, SVGLineElement | null>());
  const reducedMotion = usePrefersReducedMotion();

  const simulationBundle = useMemo<SimulationBundle | null>(() => {
    if (nodes.length === 0) return null;
    return createSimulation({
      nodes,
      edges,
      width: 1200,
      height: 800,
      previous: null,
      reducedMotion,
    });
  }, [nodes, edges, reducedMotion]);

  const simNodeMap = useMemo(() => {
    const map = new Map<string, SimNode>();
    simulationBundle?.simNodes.forEach((simNode) => map.set(simNode.id, simNode));
    return map;
  }, [simulationBundle]);

  const { neighbors: selectedNeighbors, edgeIds: selectedEdges } = useMemo(
    () => buildNeighbors(edges, selectedNodeId),
    [edges, selectedNodeId],
  );

  const bounds = useMemo<GraphBounds | null>(() => {
    if (!simulationBundle) return null;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    simulationBundle.simNodes.forEach((simNode) => {
      const r = simNode.radius + 12;
      const x = simNode.x ?? 0;
      const y = simNode.y ?? 0;
      minX = Math.min(minX, x - r);
      minY = Math.min(minY, y - r);
      maxX = Math.max(maxX, x + r);
      maxY = Math.max(maxY, y + r);
    });
    if (!Number.isFinite(minX)) return null;
    return { minX, minY, maxX, maxY };
  }, [simulationBundle]);

  const fitSignature = useMemo(
    () => `${nodes.length}:${edges.length}`,
    [nodes.length, edges.length],
  );

  const interaction = useMemoryGraphInteraction({
    containerRef,
    bounds,
    fitSignature,
    onDeselect: () => onSelectNode(null),
    onSearchFocus: onRequestSearchFocus,
  });

  const hoveredId = interaction.hoveredId;

  const { neighbors: hoveredNeighbors, edgeIds: hoveredEdges } = useMemo(
    () => buildNeighbors(edges, hoveredId),
    [edges, hoveredId],
  );

  const hasFocus = selectedNodeId != null || hoveredId != null;

  // Tick loop: mutate DOM directly each frame, no React re-renders.
  useEffect(() => {
    if (!simulationBundle) return;
    let rafId = 0;
    let running = true;

    const step = () => {
      if (!running) return;
      const { simNodes, simLinks, simulation } = simulationBundle;
      for (const simNode of simNodes) {
        const g = nodeGroupsRef.current.get(simNode.id);
        if (!g) continue;
        const x = simNode.x ?? 0;
        const y = simNode.y ?? 0;
        g.setAttribute("transform", `translate(${x} ${y})`);
        g.style.transform = `translate(${x}px, ${y}px)`;
      }
      for (const link of simLinks) {
        const line = lineRefsRef.current.get(link.id);
        if (!line) continue;
        const source = typeof link.source === "object" ? (link.source as SimNode) : null;
        const target = typeof link.target === "object" ? (link.target as SimNode) : null;
        if (!source || !target) continue;
        line.setAttribute("x1", String(source.x ?? 0));
        line.setAttribute("y1", String(source.y ?? 0));
        line.setAttribute("x2", String(target.x ?? 0));
        line.setAttribute("y2", String(target.y ?? 0));
      }
      // Continue if simulation still has energy or is targeting perpetual drift.
      const alpha = simulation.alpha();
      const target = simulation.alphaTarget();
      if (alpha > 0.001 || target > 0.001) {
        rafId = window.requestAnimationFrame(step);
      }
    };

    rafId = window.requestAnimationFrame(step);
    return () => {
      running = false;
      window.cancelAnimationFrame(rafId);
    };
  }, [simulationBundle]);

  useEffect(() => () => {
    simulationBundle?.simulation.stop();
  }, [simulationBundle]);

  const handleNodeClick = useCallback(
    (id: string) => {
      onSelectNode(id === selectedNodeId ? null : id);
    },
    [onSelectNode, selectedNodeId],
  );

  const handleNodeKey = useCallback(
    (event: ReactKeyboardEvent<SVGGElement>, id: string) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handleNodeClick(id);
      }
    },
    [handleNodeClick],
  );

  const dragStateRef = useRef<{
    nodeId: string;
    pointerId: number;
    simNode: SimNode;
  } | null>(null);

  const handleNodePointerDown = useCallback(
    (event: ReactPointerEvent<SVGGElement>, nodeId: string) => {
      if (!simulationBundle) return;
      const simNode = simNodeMap.get(nodeId);
      if (!simNode) return;
      event.stopPropagation();
      (event.currentTarget as SVGGElement).setPointerCapture(event.pointerId);
      dragStateRef.current = { nodeId, pointerId: event.pointerId, simNode };
      simNode.fx = simNode.x;
      simNode.fy = simNode.y;
      simulationBundle.simulation.alphaTarget(0.3).restart();
      event.currentTarget.setAttribute("data-dragging", "true");
    },
    [simNodeMap, simulationBundle],
  );

  const handleNodePointerMove = useCallback(
    (event: ReactPointerEvent<SVGGElement>) => {
      const state = dragStateRef.current;
      if (!state || state.pointerId !== event.pointerId) return;
      const el = containerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const screenX = event.clientX - rect.left;
      const screenY = event.clientY - rect.top;
      const vp = interaction.viewport;
      const worldX = (screenX - vp.x) / vp.scale;
      const worldY = (screenY - vp.y) / vp.scale;
      state.simNode.fx = worldX;
      state.simNode.fy = worldY;
    },
    [interaction.viewport],
  );

  const handleNodePointerUp = useCallback(
    (event: ReactPointerEvent<SVGGElement>) => {
      const state = dragStateRef.current;
      if (!state || state.pointerId !== event.pointerId) return;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      event.currentTarget.removeAttribute("data-dragging");
      state.simNode.fx = null;
      state.simNode.fy = null;
      simulationBundle?.simulation.alphaTarget(reducedMotion ? 0 : 0.02);
      dragStateRef.current = null;
    },
    [reducedMotion, simulationBundle],
  );

  const zoomLabel = Math.round(interaction.viewport.scale * 100);
  const zoomTier: "none" | "focused" | "all" =
    interaction.viewport.scale < 0.55 ? "none" : "all";

  return (
    <div
      ref={containerRef}
      className="memory-graph-surface relative flex h-full w-full overflow-hidden bg-black"
      data-panning={interaction.isPanning ? "true" : undefined}
    >
      <svg
        role="application"
        aria-label={t("memory.map.canvasAriaLabel", { defaultValue: "Mapa neural de memórias" })}
        className="memory-graph-svg absolute inset-0 h-full w-full select-none"
        onPointerDown={interaction.handleBackgroundPointerDown}
        onPointerMove={interaction.handleBackgroundPointerMove}
        onPointerUp={interaction.handleBackgroundPointerUp}
        onPointerCancel={interaction.handleBackgroundPointerUp}
      >
        <rect
          data-memory-graph-background="true"
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="transparent"
        />

        <g
          ref={worldGroupRef}
          transform={`translate(${interaction.viewport.x} ${interaction.viewport.y}) scale(${interaction.viewport.scale})`}
          style={{
            transform: `translate(${interaction.viewport.x}px, ${interaction.viewport.y}px) scale(${interaction.viewport.scale})`,
            transformOrigin: "0 0",
            transformBox: "view-box",
          }}
          className="memory-graph-world"
          data-zoom-tier={zoomTier}
        >
          {simulationBundle?.simLinks.map((link) => {
            const edge = link.edge;
            let state: EdgeInteractionState = "idle";
            if (selectedEdges.has(edge.id) || hoveredEdges.has(edge.id)) {
              state = "active";
            } else if (hasFocus) {
              state = "dimmed";
            }
            const style = getEdgeStyle(edge, state);
            const source = typeof link.source === "object" ? (link.source as SimNode) : null;
            const target = typeof link.target === "object" ? (link.target as SimNode) : null;
            return (
              <line
                key={`edge-${edge.id}`}
                ref={(el) => {
                  if (el) lineRefsRef.current.set(link.id, el);
                  else lineRefsRef.current.delete(link.id);
                }}
                x1={source?.x ?? 0}
                y1={source?.y ?? 0}
                x2={target?.x ?? 0}
                y2={target?.y ?? 0}
                stroke={style.stroke}
                strokeOpacity={style.opacity}
                strokeWidth={style.width}
                pointerEvents="none"
                className="memory-graph-edge"
              />
            );
          })}

          {simulationBundle?.simNodes.map((simNode) => {
            const node = simNode.node;
            const isSelected = node.id === selectedNodeId;
            const isHovered = hoveredId === node.id;
            let state: NodeInteractionState = "idle";
            if (isSelected) state = "selected";
            else if (isHovered) state = "hovered";
            else if (selectedNodeId && selectedNeighbors.has(node.id)) state = "neighbor";
            else if (hoveredId && hoveredNeighbors.has(node.id)) state = "neighbor";
            else if (hasFocus) state = "dimmed";

            const style = getNodeStyle(node, state);
            const radius = simNode.radius;
            const isFocused =
              state === "selected" || state === "hovered" || state === "neighbor";

            return (
              <g
                key={`node-${node.id}`}
                ref={(el) => {
                  if (el) nodeGroupsRef.current.set(node.id, el);
                  else nodeGroupsRef.current.delete(node.id);
                }}
                transform={`translate(${simNode.x ?? 0} ${simNode.y ?? 0})`}
                className={cn(
                  "memory-graph-node",
                  isFocused && "memory-graph-node--focused",
                  state === "selected" && "memory-graph-node--selected",
                )}
                tabIndex={0}
                role="button"
                aria-label={node.kind === "learning" ? `${node.title}: ${node.summary}` : node.label}
                aria-pressed={isSelected}
                onKeyDown={(event) => handleNodeKey(event, node.id)}
                onClick={() => handleNodeClick(node.id)}
                onPointerEnter={() => interaction.setHoveredId(node.id)}
                onPointerLeave={() => interaction.setHoveredId(null)}
                onPointerDown={(event) => handleNodePointerDown(event, node.id)}
                onPointerMove={handleNodePointerMove}
                onPointerUp={handleNodePointerUp}
                onPointerCancel={handleNodePointerUp}
                style={{
                  opacity: style.opacity,
                  transform: `translate(${simNode.x ?? 0}px, ${simNode.y ?? 0}px)`,
                  transformBox: "view-box",
                  transformOrigin: "0 0",
                }}
              >
                <circle
                  r={radius}
                  fill={style.fill}
                  stroke={style.stroke ?? "none"}
                  strokeWidth={style.strokeWidth}
                />
                <text
                  y={radius + 12}
                  textAnchor="middle"
                  className="memory-graph-label"
                  pointerEvents="none"
                >
                  {truncateText(
                    node.kind === "learning" ? node.title : node.label,
                    22,
                  )}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="pointer-events-auto absolute bottom-4 right-4 flex items-center gap-1 rounded-[var(--radius-pill)] border border-[color:var(--border-subtle)] bg-[color:var(--panel)] px-1.5 py-1 shadow-none">
        <button
          type="button"
          onClick={interaction.zoomOut}
          className="memory-graph-control"
          aria-label={t("memory.map.zoomOut", { defaultValue: "Diminuir zoom" })}
        >
          <Minus className="icon-xs" strokeWidth={1.75} />
        </button>
        <span className="min-w-[42px] text-center font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
          {zoomLabel}%
        </span>
        <button
          type="button"
          onClick={interaction.zoomIn}
          className="memory-graph-control"
          aria-label={t("memory.map.zoomIn", { defaultValue: "Aumentar zoom" })}
        >
          <Plus className="icon-xs" strokeWidth={1.75} />
        </button>
        <span className="mx-1 h-4 w-px bg-[color:var(--divider-hair)]" aria-hidden />
        <button
          type="button"
          onClick={interaction.fitViewport}
          className="memory-graph-control"
          aria-label={t("memory.map.reset", { defaultValue: "Recentralizar" })}
        >
          <RotateCcw className="icon-xs" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}
