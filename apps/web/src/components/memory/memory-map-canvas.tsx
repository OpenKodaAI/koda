"use client";

import {
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getMemoryTypeMeta } from "@/lib/memory-constants";
import type {
  MemoryGraphEdge,
  MemoryGraphNode,
  MemoryLearningNode,
} from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";

type MemoryNode = MemoryGraphNode | MemoryLearningNode;
type NodeVisualCategory = "document" | "memory-latest" | "memory-older";
type NodeShape = "hub" | "memory" | "document";
type RelationKind =
  | "mesh"
  | "structure"
  | "similarity"
  | "updates"
  | "extends"
  | "derives";

type PositionedNode = MemoryNode & {
  x: number;
  y: number;
  radius: number;
  width: number;
  height: number;
  clusterKey: string;
  isRoot: boolean;
  shape: NodeShape;
  visualCategory: NodeVisualCategory;
};

type LayoutEdge = {
  id: string;
  source: string;
  target: string;
  relation: RelationKind;
  path: string;
  stroke: string;
  strokeWidth: number;
  opacity: number;
  dashArray?: string;
  markerId?: string;
  layer: number;
};

type LayoutBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  width: number;
  height: number;
};

type ViewportState = {
  x: number;
  y: number;
  scale: number;
};

type ClusterLayout = {
  key: string;
  rootId: string;
  angle: number;
  centerX: number;
  centerY: number;
  nodes: PositionedNode[];
};

type GraphLayout = {
  nodes: PositionedNode[];
  edges: LayoutEdge[];
  nodeMap: Map<string, PositionedNode>;
  bounds: LayoutBounds;
  clusters: ClusterLayout[];
};

interface MemoryMapCanvasProps {
  nodes: MemoryNode[];
  edges: MemoryGraphEdge[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  storageScope?: string;
}

const MIN_SCALE = 0.45;
const MAX_SCALE = 2.15;
const WORLD_WIDTH = 1760;
const WORLD_HEIGHT = 1180;
const WORLD_CENTER_X = 860;
const WORLD_CENTER_Y = 560;
const OUTER_RING_RADIUS_X = 690;
const OUTER_RING_RADIUS_Y = 470;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function hashString(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function seededUnit(value: string) {
  return (hashString(value) % 10_000) / 10_000;
}

function getClusterKey(node: MemoryNode) {
  return node.cluster_id ?? `${node.kind}-${node.id}`;
}

function getNodeWeight(node: MemoryNode) {
  if (node.kind === "learning") {
    return node.importance * 1.75 + node.member_count * 0.42;
  }

  return node.importance * 1.25 + node.access_count * 0.06 + node.related_count * 0.28;
}

function isNewMemory(node: MemoryNode) {
  if (node.kind !== "memory" || !node.created_at) return false;
  return Date.now() - new Date(node.created_at).getTime() <= 5 * 24 * 60 * 60 * 1000;
}

function isExpiringSoon(node: MemoryNode) {
  if (node.kind !== "memory" || !node.expires_at) return false;
  const diff = new Date(node.expires_at).getTime() - Date.now();
  return diff > 0 && diff <= 7 * 24 * 60 * 60 * 1000;
}

function isForgotten(node: MemoryNode) {
  if (node.kind !== "memory") return false;
  if (node.is_active === false) return true;
  if (!node.last_accessed) return false;
  return Date.now() - new Date(node.last_accessed).getTime() > 45 * 24 * 60 * 60 * 1000;
}

function getVisualCategory(node: MemoryNode): NodeVisualCategory {
  if (node.kind === "learning") return "document";
  return isNewMemory(node) ? "memory-latest" : "memory-older";
}

function getNodeStroke(node: MemoryNode, visualCategory: NodeVisualCategory) {
  if (node.kind === "learning") {
    return "rgba(206,214,226,0.34)";
  }

  if (isForgotten(node)) return "rgba(226,124,124,0.74)";
  if (isExpiringSoon(node)) return "rgba(232,178,75,0.84)";
  if (visualCategory === "memory-latest") return "rgba(99,208,149,0.8)";
  return "rgba(134,160,205,0.72)";
}

function getNodeFill(node: MemoryNode, visualCategory: NodeVisualCategory) {
  if (node.kind === "learning") {
    return "rgba(19,24,30,0.96)";
  }

  if (isForgotten(node)) return "rgba(58,24,30,0.7)";
  if (isExpiringSoon(node)) return "rgba(67,49,18,0.74)";
  if (visualCategory === "memory-latest") return "rgba(18,39,31,0.74)";
  return "rgba(14,22,30,0.78)";
}

function createCurvePath(
  source: { x: number; y: number },
  target: { x: number; y: number },
  curve = 0.16
) {
  const middleX = (source.x + target.x) / 2;
  const middleY = (source.y + target.y) / 2;
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.hypot(dx, dy) || 1;
  const normalX = -dy / distance;
  const normalY = dx / distance;
  const bend = Math.min(82, distance * curve);

  return `M ${source.x} ${source.y} Q ${middleX + normalX * bend} ${middleY + normalY * bend}, ${target.x} ${target.y}`;
}

function getClusterAnchor(index: number, total: number) {
  const innerAnchors = [
    { x: WORLD_CENTER_X - 320, y: WORLD_CENTER_Y + 14, angle: 3.5 },
    { x: WORLD_CENTER_X + 58, y: WORLD_CENTER_Y - 96, angle: -0.55 },
    { x: WORLD_CENTER_X + 126, y: WORLD_CENTER_Y + 186, angle: 0.62 },
  ];

  if (index < innerAnchors.length) {
    return innerAnchors[index];
  }

  const outerCount = Math.max(1, total - innerAnchors.length);
  const angle =
    -Math.PI / 2 + ((index - innerAnchors.length) / outerCount) * Math.PI * 2;

  return {
    x: WORLD_CENTER_X + Math.cos(angle) * OUTER_RING_RADIUS_X,
    y: WORLD_CENTER_Y + Math.sin(angle) * OUTER_RING_RADIUS_Y,
    angle,
  };
}

function fitViewport(
  bounds: LayoutBounds,
  size: { width: number; height: number },
  reservedWidth: number
) {
  const usableWidth = Math.max(260, size.width - reservedWidth - 56);
  const usableHeight = Math.max(300, size.height - 56);
  const scale = clamp(
    Math.min(usableWidth / bounds.width, usableHeight / bounds.height),
    MIN_SCALE,
    MAX_SCALE
  );

  const viewportCenterX = reservedWidth > 0 ? (size.width - reservedWidth) / 2 : size.width / 2;
  const viewportCenterY = size.height / 2;

  return {
    scale,
    x: viewportCenterX - (bounds.minX + bounds.width / 2) * scale,
    y: viewportCenterY - (bounds.minY + bounds.height / 2) * scale,
  };
}

function formatNodeTitle(node: MemoryNode) {
  return node.kind === "learning" ? node.title : node.label;
}

function formatNodePreview(node: MemoryNode, emptyLabel: string) {
  if (node.kind === "learning") return truncateText(node.summary, 150);
  return truncateText(
    node.content || node.source_query_preview || node.source_query_text || emptyLabel,
    150
  );
}

export function MemoryMapCanvas({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  storageScope,
}: MemoryMapCanvasProps) {
  const { t } = useAppI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef<ViewportState>({ x: 0, y: 0, scale: 1 });
  const panningRef = useRef<{ pointerId: number; startX: number; startY: number } | null>(null);
  const markerPrefix = useId().replace(/:/g, "");

  const [size, setSize] = useState({ width: 1120, height: 760 });
  const [viewport, setViewport] = useState<ViewportState>({ x: 0, y: 0, scale: 1 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const [isolatedClusterId, setIsolatedClusterId] = useState<string | null>(null);

  useEffect(() => {
    viewportRef.current = viewport;
  }, [viewport]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setSize({
        width: Math.max(320, Math.round(entry.contentRect.width)),
        height: Math.max(480, Math.round(entry.contentRect.height)),
      });
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const graph = useMemo(() => {
    const scopedIsolationKey =
      isolatedClusterId != null && storageScope ? `${storageScope}::${isolatedClusterId}` : null;
    const activeCluster =
      isolatedClusterId &&
      nodes.some(
        (node) =>
          node.cluster_id === isolatedClusterId &&
          (scopedIsolationKey == null || `${storageScope}::${node.cluster_id}` === scopedIsolationKey)
      )
        ? isolatedClusterId
        : null;

    const filteredNodes =
      activeCluster == null
        ? nodes
        : nodes.filter((node) => node.cluster_id === activeCluster);
    const visibleIds = new Set(filteredNodes.map((node) => node.id));

    return {
      nodes: filteredNodes,
      edges: edges.filter(
        (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)
      ),
      activeCluster,
    };
  }, [edges, isolatedClusterId, nodes, storageScope]);

  const layout = useMemo<GraphLayout>(() => {
    const grouped = new Map<
      string,
      { key: string; learnings: MemoryLearningNode[]; memories: MemoryGraphNode[] }
    >();

    graph.nodes.forEach((node) => {
      const key = getClusterKey(node);
      const entry = grouped.get(key) ?? {
        key,
        learnings: [],
        memories: [],
      };

      if (node.kind === "learning") {
        entry.learnings.push(node);
      } else {
        entry.memories.push(node);
      }

      grouped.set(key, entry);
    });

    const orderedClusters = Array.from(grouped.values()).sort((left, right) => {
      const leftWeight =
        left.learnings.reduce((sum, node) => sum + getNodeWeight(node), 0) +
        left.memories.reduce((sum, node) => sum + getNodeWeight(node), 0);
      const rightWeight =
        right.learnings.reduce((sum, node) => sum + getNodeWeight(node), 0) +
        right.memories.reduce((sum, node) => sum + getNodeWeight(node), 0);

      return rightWeight - leftWeight;
    });

    const positionedNodes: PositionedNode[] = [];
    const clusterLayouts: ClusterLayout[] = [];

    orderedClusters.forEach((cluster, index) => {
      const rootSource =
        [...cluster.learnings].sort((a, b) => getNodeWeight(b) - getNodeWeight(a))[0] ??
        [...cluster.memories].sort((a, b) => getNodeWeight(b) - getNodeWeight(a))[0];

      if (!rootSource) return;

      const anchor = getClusterAnchor(index, orderedClusters.length);
      const clusterNodes: PositionedNode[] = [];

      const rootRadius = clamp(
        rootSource.kind === "learning"
          ? 12 + rootSource.member_count * 0.11 + rootSource.importance * 7
          : 10 + rootSource.importance * 6,
        11,
        18
      );

      clusterNodes.push({
        ...rootSource,
        x: anchor.x,
        y: anchor.y,
        radius: rootRadius,
        width: rootRadius * 2,
        height: rootRadius * 2,
        clusterKey: cluster.key,
        isRoot: true,
        shape: "hub",
        visualCategory: getVisualCategory(rootSource),
      });

      const nonRootNodes = [...cluster.learnings, ...cluster.memories]
        .filter((node) => node.id !== rootSource.id)
        .sort((left, right) => getNodeWeight(right) - getNodeWeight(left));

      nonRootNodes.forEach((node, nodeIndex) => {
        const seed = seededUnit(node.id);
        const band = Math.floor(nodeIndex / 14);
        const bandIndex = nodeIndex % 14;
        const distance =
          (node.kind === "learning" ? 110 : 86) + band * 52 + (seed - 0.5) * 22;
        const angle =
          anchor.angle +
          bandIndex * GOLDEN_ANGLE +
          band * 0.38 +
          (seed - 0.5) * 0.9;
        const radius = clamp(
          node.kind === "learning"
            ? 7.5 + node.importance * 2.8
            : 4.8 + node.importance * 2.6 + Math.min(1.6, node.related_count * 0.08),
          node.kind === "learning" ? 7 : 4.5,
          node.kind === "learning" ? 10.5 : 8.2
        );
        const width = node.kind === "learning" ? radius * 2.8 : radius * 2;
        const height = node.kind === "learning" ? radius * 1.12 : radius * 2;

        clusterNodes.push({
          ...node,
          x: anchor.x + Math.cos(angle) * distance,
          y: anchor.y + Math.sin(angle) * distance * 0.92,
          radius,
          width,
          height,
          clusterKey: cluster.key,
          isRoot: false,
          shape: node.kind === "learning" ? "document" : "memory",
          visualCategory: getVisualCategory(node),
        });
      });

      clusterLayouts.push({
        key: cluster.key,
        rootId: rootSource.id,
        angle: anchor.angle,
        centerX: anchor.x,
        centerY: anchor.y,
        nodes: clusterNodes,
      });

      positionedNodes.push(...clusterNodes);
    });

    const nodeMap = new Map(positionedNodes.map((node) => [node.id, node]));
    const layoutEdges: LayoutEdge[] = [];
    const structurePairs = new Set<string>();

    clusterLayouts.forEach((cluster) => {
      const root = nodeMap.get(cluster.rootId);
      if (!root) return;

      cluster.nodes.forEach((node) => {
        if (node.id === root.id) return;
        structurePairs.add([root.id, node.id].sort().join("::"));
        layoutEdges.push({
          id: `structure-${root.id}-${node.id}`,
          source: root.id,
          target: node.id,
          relation: "structure",
          path: createCurvePath(root, node, 0.08),
          stroke: "rgba(132,146,163,0.22)",
          strokeWidth: 1.1,
          opacity: 0.7,
          layer: 1,
        });
      });
    });

    graph.edges.forEach((edge) => {
      const source = nodeMap.get(edge.source);
      const target = nodeMap.get(edge.target);
      if (!source || !target) return;

      const pairKey = [edge.source, edge.target].sort().join("::");
      if (edge.type === "learning" && structurePairs.has(pairKey)) return;

      const isSimilarity = edge.type === "learning";
      const relation: RelationKind =
        edge.type === "source"
          ? "updates"
          : edge.type === "session"
            ? "extends"
            : edge.type === "semantic"
              ? "derives"
              : "similarity";

      const similarityStrength =
        edge.similarity == null ? 0.42 : clamp(edge.similarity, 0.12, 0.98);
      const opacity =
        relation === "updates"
          ? 0.78
          : relation === "extends"
            ? 0.58
            : relation === "derives"
              ? 0.54
              : 0.34 + similarityStrength * 0.2;

      layoutEdges.push({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        relation,
        path: createCurvePath(source, target, isSimilarity ? 0.12 : 0.18),
        stroke:
          relation === "updates"
            ? "rgba(135,94,255,0.92)"
            : relation === "extends"
              ? "rgba(85,188,127,0.82)"
              : relation === "derives"
                ? "rgba(114,140,224,0.82)"
                : "rgba(152,163,178,0.28)",
        strokeWidth:
          relation === "updates"
            ? 1.5
            : relation === "extends"
              ? 1.35
              : relation === "derives"
                ? 1.25
                : 1.05,
        opacity,
        dashArray: relation === "similarity" ? "6 8" : undefined,
        markerId:
          relation === "updates" || relation === "extends" || relation === "derives"
            ? `${markerPrefix}-${relation}`
            : undefined,
        layer: relation === "similarity" ? 0 : 2,
      });
    });

    clusterLayouts.forEach((cluster, index) => {
      const source = nodeMap.get(cluster.rootId);
      if (!source) return;

      const neighborIndices = [index + 1, index + 2];
      neighborIndices.forEach((neighborIndex) => {
        const targetCluster = clusterLayouts[neighborIndex % clusterLayouts.length];
        if (!targetCluster || targetCluster.key === cluster.key) return;

        const target = nodeMap.get(targetCluster.rootId);
        if (!target) return;

        layoutEdges.push({
          id: `mesh-${cluster.rootId}-${targetCluster.rootId}`,
          source: source.id,
          target: target.id,
          relation: "mesh",
          path: createCurvePath(source, target, 0.06),
          stroke: "rgba(92,106,122,0.14)",
          strokeWidth: 0.9,
          opacity: 0.75,
          layer: 0,
        });
      });
    });

    if (positionedNodes.length === 0) {
      return {
        nodes: [],
        edges: [],
        nodeMap,
        clusters: [],
        bounds: {
          minX: 0,
          minY: 0,
          maxX: WORLD_WIDTH,
          maxY: WORLD_HEIGHT,
          width: WORLD_WIDTH,
          height: WORLD_HEIGHT,
        },
      };
    }

    const minX = Math.min(...positionedNodes.map((node) => node.x - node.width * 1.7));
    const minY = Math.min(...positionedNodes.map((node) => node.y - node.height * 1.7));
    const maxX = Math.max(...positionedNodes.map((node) => node.x + node.width * 1.7));
    const maxY = Math.max(...positionedNodes.map((node) => node.y + node.height * 1.7));

    return {
      nodes: positionedNodes,
      edges: layoutEdges.sort((left, right) => left.layer - right.layer),
      nodeMap,
      clusters: clusterLayouts,
      bounds: {
        minX,
        minY,
        maxX,
        maxY,
        width: Math.max(960, maxX - minX),
        height: Math.max(720, maxY - minY),
      },
    };
  }, [graph.edges, graph.nodes, markerPrefix]);

  const selectedNode = selectedNodeId ? layout.nodeMap.get(selectedNodeId) ?? null : null;
  const selectedClusterId = selectedNode?.cluster_id ?? null;
  const relatedNodeIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();

    const ids = new Set<string>([selectedNodeId]);
    layout.edges.forEach((edge) => {
      if (edge.source === selectedNodeId || edge.target === selectedNodeId) {
        ids.add(edge.source);
        ids.add(edge.target);
      }
    });
    return ids;
  }, [layout.edges, selectedNodeId]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const handleWheel = (event: WheelEvent) => {
      if (!(event.target instanceof Node) || !element.contains(event.target)) return;

      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const cursorX = event.clientX - rect.left;
      const cursorY = event.clientY - rect.top;

      setViewport((current) => {
        const nextScale = clamp(
          current.scale * (event.deltaY > 0 ? 0.92 : 1.08),
          MIN_SCALE,
          MAX_SCALE
        );
        if (nextScale === current.scale) return current;

        const scaleRatio = nextScale / current.scale;
        return {
          scale: nextScale,
          x: cursorX - (cursorX - current.x) * scaleRatio,
          y: cursorY - (cursorY - current.y) * scaleRatio,
        };
      });
    };

    element.addEventListener("wheel", handleWheel, { passive: false });
    return () => element.removeEventListener("wheel", handleWheel);
  }, []);

  const fitSignature = `${graph.activeCluster ?? "all"}:${layout.nodes.length}:${layout.edges.length}:${size.width}x${size.height}`;

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setViewport(
        fitViewport(layout.bounds, size, size.width >= 1280 ? 308 : size.width >= 960 ? 280 : 0)
      );
    });

    return () => window.cancelAnimationFrame(frame);
  }, [fitSignature, layout.bounds, size]);

  const handleBackgroundPointerDown = (
    event: ReactPointerEvent<SVGSVGElement>
  ) => {
    const target = event.target;
    const isBackground =
      target === event.currentTarget ||
      (target instanceof SVGRectElement &&
        target.dataset.memoryMapBackground === "true");

    if (!isBackground) return;

    onSelectNode(null);
    setHoveredNodeId(null);
    setIsPanning(true);
    panningRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX - viewportRef.current.x,
      startY: event.clientY - viewportRef.current.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleBackgroundPointerMove = (
    event: ReactPointerEvent<SVGSVGElement>
  ) => {
    const activePan = panningRef.current;
    if (!activePan || activePan.pointerId !== event.pointerId) return;

    setViewport((current) => ({
      ...current,
      x: event.clientX - activePan.startX,
      y: event.clientY - activePan.startY,
    }));
  };

  const releasePan = (event: ReactPointerEvent<SVGSVGElement>) => {
    const activePan = panningRef.current;
    if (!activePan || activePan.pointerId !== event.pointerId) return;

    panningRef.current = null;
    setIsPanning(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const resetMap = () => {
    setHoveredNodeId(null);
    setIsolatedClusterId(null);
    onSelectNode(null);
    setViewport(
      fitViewport(layout.bounds, size, size.width >= 1280 ? 308 : size.width >= 960 ? 280 : 0)
    );
  };

  const memoryCount = layout.nodes.filter((node) => node.kind === "memory").length;
  const documentCount = layout.nodes.filter((node) => node.kind === "learning").length;
  const connectionCount = layout.edges.filter((edge) => edge.relation !== "mesh").length;
  const forgottenCount = layout.nodes.filter((node) => isForgotten(node)).length;
  const expiringSoonCount = layout.nodes.filter((node) => isExpiringSoon(node)).length;
  const newMemoryCount = layout.nodes.filter((node) => isNewMemory(node)).length;

  return (
    <div className="relative h-[480px] overflow-hidden rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[#0a1016] sm:h-[620px] lg:h-[740px] xl:h-[820px] 2xl:h-[900px]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_25%_18%,rgba(91,119,173,0.08),transparent_28%),radial-gradient(circle_at_72%_68%,rgba(118,88,232,0.08),transparent_24%),linear-gradient(180deg,#0c1319_0%,#0a1117_100%)]" />

      <div className="absolute left-4 top-4 z-30 flex items-center gap-2">
        <button
          type="button"
          onClick={() =>
            setViewport((current) => ({
              ...current,
              scale: clamp(current.scale * 1.1, MIN_SCALE, MAX_SCALE),
            }))
          }
          className="memory-map-control"
          aria-label={t("memory.map.zoomIn")}
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() =>
            setViewport((current) => ({
              ...current,
              scale: clamp(current.scale * 0.9, MIN_SCALE, MAX_SCALE),
            }))
          }
          className="memory-map-control"
          aria-label={t("memory.map.zoomOut")}
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={resetMap}
          className="memory-map-control"
          aria-label={t("memory.map.reset")}
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      <div
        ref={containerRef}
        className={cn(
          "relative h-full w-full overflow-hidden touch-none",
          isPanning ? "cursor-grabbing" : "cursor-grab"
        )}
      >
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox={`0 0 ${size.width} ${size.height}`}
          onPointerDown={handleBackgroundPointerDown}
          onPointerMove={handleBackgroundPointerMove}
          onPointerUp={releasePan}
          onPointerCancel={releasePan}
          onPointerLeave={() => setHoveredNodeId(null)}
        >
          <defs>
            <pattern
              id={`${markerPrefix}-grid`}
              width="28"
              height="28"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 28 0 L 0 0 0 28"
                fill="none"
                stroke="rgba(181,191,206,0.045)"
                strokeWidth="1"
              />
            </pattern>
            <pattern
              id={`${markerPrefix}-grid-strong`}
              width="112"
              height="112"
              patternUnits="userSpaceOnUse"
            >
              <rect width="112" height="112" fill={`url(#${markerPrefix}-grid)`} />
              <path
                d="M 112 0 L 0 0 0 112"
                fill="none"
                stroke="rgba(181,191,206,0.055)"
                strokeWidth="1"
              />
            </pattern>
            <filter
              id={`${markerPrefix}-hub-glow`}
              x="-200%"
              y="-200%"
              width="400%"
              height="400%"
            >
              <feGaussianBlur stdDeviation="10" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {[
              { id: "updates", color: "rgba(135,94,255,0.95)" },
              { id: "extends", color: "rgba(85,188,127,0.92)" },
              { id: "derives", color: "rgba(114,140,224,0.92)" },
            ].map((marker) => (
              <marker
                key={marker.id}
                id={`${markerPrefix}-${marker.id}`}
                markerWidth="7"
                markerHeight="7"
                refX="5.6"
                refY="3.5"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M 0 0 L 7 3.5 L 0 7 z" fill={marker.color} />
              </marker>
            ))}
          </defs>

          <rect
            data-memory-map-background="true"
            width={size.width}
            height={size.height}
            fill={`url(#${markerPrefix}-grid-strong)`}
          />

          <g
            transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}
          >
            {layout.edges.map((edge) => {
              const source = layout.nodeMap.get(edge.source);
              const target = layout.nodeMap.get(edge.target);
              if (!source || !target) return null;

              const selectedInPath =
                selectedNodeId != null &&
                (edge.source === selectedNodeId || edge.target === selectedNodeId);
              const sameCluster =
                selectedClusterId != null &&
                source.cluster_id === selectedClusterId &&
                target.cluster_id === selectedClusterId;
              const muted =
                selectedNodeId != null &&
                !selectedInPath &&
                !(edge.relation === "mesh" && sameCluster) &&
                (!relatedNodeIds.has(edge.source) || !relatedNodeIds.has(edge.target));

              return (
                <path
                  key={edge.id}
                  d={edge.path}
                  fill="none"
                  stroke={edge.stroke}
                  strokeWidth={edge.strokeWidth}
                  strokeOpacity={
                    muted
                      ? edge.relation === "mesh"
                        ? 0.035
                        : 0.08
                      : selectedInPath
                        ? 1
                        : sameCluster && edge.relation !== "mesh"
                          ? Math.min(1, edge.opacity + 0.08)
                          : edge.opacity
                  }
                  strokeDasharray={edge.dashArray}
                  markerEnd={edge.markerId ? `url(#${edge.markerId})` : undefined}
                  vectorEffect="non-scaling-stroke"
                  className={cn(
                    "memory-map-connection",
                    edge.relation === "structure" || edge.relation === "mesh"
                      ? "memory-map-connection--secondary"
                      : "memory-map-connection--primary"
                  )}
                />
              );
            })}

            {layout.nodes.map((node) => {
              const isSelected = node.id === selectedNodeId;
              const isHovered = node.id === hoveredNodeId;
              const selectedCluster =
                selectedClusterId != null && node.cluster_id === selectedClusterId;
              const muted =
                selectedNodeId != null &&
                !isSelected &&
                !selectedCluster &&
                !relatedNodeIds.has(node.id);
              const meta =
                node.kind === "learning"
                  ? getMemoryTypeMeta(node.dominant_type)
                  : getMemoryTypeMeta(node.memory_type);
              const stroke = getNodeStroke(node, node.visualCategory);
              const fill = getNodeFill(node, node.visualCategory);
              const emphasis = isSelected ? 1 : isHovered ? 0.75 : 0;

              return (
                <g
                  key={node.id}
                  role="button"
                  tabIndex={0}
                  aria-label={formatNodeTitle(node)}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelectNode(isSelected ? null : node.id);
                  }}
                  onDoubleClick={(event) => {
                    event.stopPropagation();
                    if (!node.cluster_id) return;
                    setIsolatedClusterId((current) =>
                      current === node.cluster_id ? null : node.cluster_id
                    );
                    onSelectNode(node.id);
                  }}
                  onKeyDown={(event: ReactKeyboardEvent<SVGGElement>) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectNode(isSelected ? null : node.id);
                    }
                  }}
                  onPointerEnter={() => setHoveredNodeId(node.id)}
                  onPointerLeave={() => setHoveredNodeId((current) => (current === node.id ? null : current))}
                  className="cursor-pointer outline-none"
                  transform={`translate(${node.x} ${node.y})`}
                  opacity={muted ? 0.18 : 1}
                >
                  {node.shape === "hub" ? (
                    <>
                      <circle
                        r={node.radius * 2.7}
                        fill={
                          node.kind === "learning"
                            ? "rgba(240,243,249,0.14)"
                            : "rgba(212,225,244,0.11)"
                        }
                        filter={`url(#${markerPrefix}-hub-glow)`}
                        opacity={0.58 + emphasis * 0.24}
                      />
                      <circle
                        r={node.radius * 1.22}
                        fill="rgba(236,239,244,0.2)"
                        stroke="rgba(255,255,255,0.22)"
                        strokeWidth="1.2"
                        vectorEffect="non-scaling-stroke"
                      />
                      <circle
                        r={node.radius * 0.74}
                        fill="rgba(247,249,252,0.92)"
                        stroke={meta.color}
                        strokeWidth={isSelected ? 2.4 : 1.4}
                        vectorEffect="non-scaling-stroke"
                      />
                    </>
                  ) : node.shape === "document" ? (
                    <>
                      <rect
                        x={-(node.width / 2 + 6)}
                        y={-(node.height / 2 + 5)}
                        width={node.width + 12}
                        height={node.height + 10}
                        rx={node.height / 2 + 4}
                        fill="transparent"
                      />
                      <rect
                        x={-node.width / 2}
                        y={-node.height / 2}
                        width={node.width}
                        height={node.height}
                        rx={node.height / 2}
                        fill="rgba(23,31,39,0.94)"
                        stroke={isSelected ? "rgba(255,255,255,0.56)" : stroke}
                        strokeWidth={isSelected ? 2 : 1.15}
                        vectorEffect="non-scaling-stroke"
                      />
                    </>
                  ) : (
                    <>
                      <circle r={node.radius + 6.5} fill="transparent" />
                      <circle
                        r={node.radius}
                        fill={fill}
                        stroke={isSelected ? meta.color : stroke}
                        strokeWidth={isSelected ? 2.3 : 1.45}
                        vectorEffect="non-scaling-stroke"
                      />
                      {(isSelected || isHovered) && (
                        <circle
                          r={node.radius + 3.8}
                          fill="none"
                          stroke={meta.color}
                          strokeOpacity={isSelected ? 0.5 : 0.26}
                          strokeWidth="1"
                          vectorEffect="non-scaling-stroke"
                        />
                      )}
                    </>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        <aside className="pointer-events-auto absolute bottom-3 left-3 right-3 z-30 max-h-[44%] overflow-y-auto rounded-[calc(var(--radius-panel)-0.125rem)] border border-[rgba(196,205,218,0.16)] bg-[rgba(20,26,33,0.9)] p-4 shadow-[0_18px_50px_rgba(0,0,0,0.24)] backdrop-blur-[18px] sm:bottom-4 sm:left-4 sm:right-4 sm:max-h-[52%] sm:p-5 md:left-auto md:right-5 md:top-5 md:max-h-[calc(100%-2.5rem)] md:w-[284px]">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-[1.02rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {t("memory.map.legend")}
            </h3>
            {graph.activeCluster ? (
              <span className="rounded-full border border-[rgba(196,205,218,0.14)] bg-[rgba(255,255,255,0.03)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                {t("memory.map.isolatedCluster")}
              </span>
            ) : null}
          </div>

          <div className="mt-5 space-y-5 text-[var(--text-secondary)]">
            <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
              <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.statistics")}</p>
              <div className="space-y-2.5 text-[15px]">
                <div className="flex items-center gap-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-[rgba(132,160,210,0.92)]" />
                  <span>{t("memory.map.memoryCount", { count: memoryCount })}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-[rgba(236,240,247,0.92)]" />
                  <span>{t("memory.map.documentsCount", { count: documentCount })}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-[rgba(156,166,180,0.72)]" />
                  <span>{t("memory.map.connectionsCount", { count: connectionCount })}</span>
                </div>
              </div>
            </section>

            <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
              <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.nodes")}</p>
              <div className="space-y-3 text-[15px]">
                <div className="flex items-center gap-3">
                  <span className="h-4.5 w-4.5 rounded-[5px] border border-[rgba(206,214,226,0.36)] bg-[rgba(23,31,39,0.96)]" />
                  <span>{t("memory.map.document")}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="h-4.5 w-4.5 rounded-full border border-[rgba(99,208,149,0.88)] bg-[rgba(18,39,31,0.84)]" />
                  <span>{t("memory.map.memoryLatest")}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="h-4.5 w-4.5 rounded-full border border-[rgba(134,160,205,0.76)] bg-[rgba(14,22,30,0.9)]" />
                  <span>{t("memory.map.memoryOlder")}</span>
                </div>
              </div>
            </section>

            <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
              <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.statusTitle")}</p>
              <div className="space-y-2.5 text-[15px]">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="h-4.5 w-4.5 rounded-full border border-[rgba(226,124,124,0.8)] bg-[rgba(58,24,30,0.72)]" />
                    <span>{t("memory.map.forgotten")}</span>
                  </div>
                  <span className="text-[13px] text-[var(--text-tertiary)]">{forgottenCount}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="h-4.5 w-4.5 rounded-full border border-[rgba(232,178,75,0.88)] bg-[rgba(67,49,18,0.76)]" />
                    <span>{t("memory.map.expiringSoon")}</span>
                  </div>
                  <span className="text-[13px] text-[var(--text-tertiary)]">{expiringSoonCount}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="h-4.5 w-4.5 rounded-full border border-[rgba(99,208,149,0.88)] bg-[rgba(18,39,31,0.84)]" />
                    <span>{t("memory.map.newMemory")}</span>
                  </div>
                  <span className="text-[13px] text-[var(--text-tertiary)]">{newMemoryCount}</span>
                </div>
              </div>
            </section>

            <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
              <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.connectionsTitle")}</p>
              <div className="space-y-3 text-[15px]">
                <div className="flex items-center gap-3">
                  <span className="block h-px w-8 bg-[rgba(168,178,190,0.72)]" />
                  <span>{t("memory.map.docToMemory")}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="block h-px w-8 border-t border-dashed border-[rgba(168,178,190,0.68)]" />
                  <span>{t("memory.map.docSimilarity")}</span>
                </div>
              </div>
            </section>

            <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
              <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.relationsTitle")}</p>
              <div className="space-y-3 text-[15px]">
                <div className="flex items-center gap-3">
                  <span className="block h-px w-8 bg-[rgba(135,94,255,0.94)]" />
                  <span className="text-[rgba(176,148,255,0.92)]">{t("memory.map.relationUpdates")}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="block h-px w-8 bg-[rgba(85,188,127,0.92)]" />
                  <span className="text-[rgba(118,212,156,0.92)]">{t("memory.map.relationExtends")}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="block h-px w-8 bg-[rgba(114,140,224,0.92)]" />
                  <span className="text-[rgba(150,170,234,0.9)]">{t("memory.map.relationDerives")}</span>
                </div>
              </div>
            </section>

            <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
              <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.similarityTitle")}</p>
              <div className="space-y-2.5 text-[15px]">
                <div className="flex items-center gap-3">
                  <span className="h-4.5 w-4.5 rounded-full bg-[rgba(74,82,94,0.64)]" />
                  <span>{t("memory.map.weak")}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="h-4.5 w-4.5 rounded-full bg-[rgba(157,168,182,0.86)]" />
                  <span>{t("memory.map.strong")}</span>
                </div>
              </div>
            </section>

            {selectedNode ? (
              <section className="space-y-3 border-t border-[rgba(255,255,255,0.08)] pt-5">
                <p className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.map.currentFocus")}</p>
                <div className="rounded-[var(--radius-panel-sm)] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-3.5 py-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{
                        backgroundColor:
                          selectedNode.kind === "learning"
                            ? getMemoryTypeMeta(selectedNode.dominant_type).color
                            : getMemoryTypeMeta(selectedNode.memory_type).color,
                      }}
                    />
                    <span className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
                      {selectedNode.kind === "learning" ? t("memory.map.learning") : t("memory.map.memory")}
                    </span>
                  </div>
                  <p className="mt-2 text-[15px] font-medium leading-6 text-[var(--text-primary)]">
                    {formatNodeTitle(selectedNode)}
                  </p>
                  <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                    {formatNodePreview(selectedNode, t("memory.map.noContentAvailable"))}
                  </p>
                </div>
              </section>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}
