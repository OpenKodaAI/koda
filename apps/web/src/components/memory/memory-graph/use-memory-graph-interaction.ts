"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { clamp } from "./memory-graph-visuals";

const MIN_SCALE = 0.45;
const MAX_SCALE = 2.6;
const WHEEL_STEP = 0.08;
const KEYBOARD_PAN_STEP = 48;
const KEYBOARD_ZOOM_STEP = 0.12;

export interface Viewport {
  x: number;
  y: number;
  scale: number;
}

export interface GraphBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface InteractionOptions {
  containerRef: React.RefObject<HTMLElement | null>;
  bounds: GraphBounds | null;
  fitSignature: string;
  onDeselect: () => void;
  onSearchFocus?: () => void;
}

export interface InteractionState {
  viewport: Viewport;
  hoveredId: string | null;
  isPanning: boolean;
  size: { width: number; height: number };
  setHoveredId: (id: string | null) => void;
  fitViewport: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  panBy: (dx: number, dy: number) => void;
  handleBackgroundPointerDown: (event: ReactPointerEvent<SVGSVGElement>) => void;
  handleBackgroundPointerMove: (event: ReactPointerEvent<SVGSVGElement>) => void;
  handleBackgroundPointerUp: (event: ReactPointerEvent<SVGSVGElement>) => void;
}

function clampScale(value: number) {
  return clamp(value, MIN_SCALE, MAX_SCALE);
}

const FIT_MAX_SCALE = 1.1;

function fitToBounds(
  bounds: GraphBounds,
  size: { width: number; height: number },
): Viewport {
  const width = Math.max(10, bounds.maxX - bounds.minX);
  const height = Math.max(10, bounds.maxY - bounds.minY);
  const padding = 96;
  const rawScale = Math.min(
    (size.width - padding) / width,
    (size.height - padding) / height,
  );
  const scale = clamp(rawScale, MIN_SCALE, Math.min(MAX_SCALE, FIT_MAX_SCALE));
  return {
    scale,
    x: size.width / 2 - ((bounds.minX + bounds.maxX) / 2) * scale,
    y: size.height / 2 - ((bounds.minY + bounds.maxY) / 2) * scale,
  };
}

export function useMemoryGraphInteraction(options: InteractionOptions): InteractionState {
  const { containerRef, bounds, fitSignature, onDeselect, onSearchFocus } = options;

  const [size, setSize] = useState({ width: 1120, height: 720 });
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, scale: 1 });
  const [hoveredId, setHoveredIdState] = useState<string | null>(null);
  const [isPanning, setIsPanning] = useState(false);

  const viewportRef = useRef(viewport);
  const panRef = useRef<{ pointerId: number; startX: number; startY: number } | null>(null);
  const pendingHoverRef = useRef<string | null>(null);
  const hoverFrameRef = useRef<number | null>(null);

  useEffect(() => {
    viewportRef.current = viewport;
  }, [viewport]);

  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setSize({
        width: Math.max(320, Math.round(entry.contentRect.width)),
        height: Math.max(420, Math.round(entry.contentRect.height)),
      });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [containerRef]);

  useEffect(() => {
    if (!bounds) return;
    const frame = window.requestAnimationFrame(() => {
      setViewport(fitToBounds(bounds, size));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [bounds, fitSignature, size]);

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
        const factor = event.deltaY > 0 ? 1 - WHEEL_STEP : 1 + WHEEL_STEP;
        const nextScale = clampScale(current.scale * factor);
        if (nextScale === current.scale) return current;
        const ratio = nextScale / current.scale;
        return {
          scale: nextScale,
          x: cursorX - (cursorX - current.x) * ratio,
          y: cursorY - (cursorY - current.y) * ratio,
        };
      });
    };
    element.addEventListener("wheel", handleWheel, { passive: false });
    return () => element.removeEventListener("wheel", handleWheel);
  }, [containerRef]);

  const setHoveredId = useCallback((id: string | null) => {
    pendingHoverRef.current = id;
    if (hoverFrameRef.current != null) return;
    hoverFrameRef.current = window.requestAnimationFrame(() => {
      hoverFrameRef.current = null;
      setHoveredIdState(pendingHoverRef.current);
    });
  }, []);

  const fitViewport = useCallback(() => {
    if (!bounds) return;
    setViewport(fitToBounds(bounds, size));
  }, [bounds, size]);

  const zoomIn = useCallback(() => {
    setViewport((current) => {
      const nextScale = clampScale(current.scale + KEYBOARD_ZOOM_STEP);
      if (nextScale === current.scale) return current;
      const ratio = nextScale / current.scale;
      const cx = size.width / 2;
      const cy = size.height / 2;
      return {
        scale: nextScale,
        x: cx - (cx - current.x) * ratio,
        y: cy - (cy - current.y) * ratio,
      };
    });
  }, [size.height, size.width]);

  const zoomOut = useCallback(() => {
    setViewport((current) => {
      const nextScale = clampScale(current.scale - KEYBOARD_ZOOM_STEP);
      if (nextScale === current.scale) return current;
      const ratio = nextScale / current.scale;
      const cx = size.width / 2;
      const cy = size.height / 2;
      return {
        scale: nextScale,
        x: cx - (cx - current.x) * ratio,
        y: cy - (cy - current.y) * ratio,
      };
    });
  }, [size.height, size.width]);

  const panBy = useCallback((dx: number, dy: number) => {
    setViewport((current) => ({
      ...current,
      x: current.x + dx,
      y: current.y + dy,
    }));
  }, []);

  const handleBackgroundPointerDown = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      const target = event.target as SVGElement | null;
      const isBackground =
        target === event.currentTarget ||
        (target instanceof SVGRectElement && target.dataset.memoryGraphBackground === "true");
      if (!isBackground) return;

      onDeselect();
      setHoveredId(null);
      setIsPanning(true);
      panRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX - viewportRef.current.x,
        startY: event.clientY - viewportRef.current.y,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [onDeselect, setHoveredId],
  );

  const handleBackgroundPointerMove = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    const active = panRef.current;
    if (!active || active.pointerId !== event.pointerId) return;
    setViewport((current) => ({
      ...current,
      x: event.clientX - active.startX,
      y: event.clientY - active.startY,
    }));
  }, []);

  const handleBackgroundPointerUp = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    const active = panRef.current;
    if (!active || active.pointerId !== event.pointerId) return;
    panRef.current = null;
    setIsPanning(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      const activeTag = (document.activeElement?.tagName ?? "").toLowerCase();
      if (activeTag === "input" || activeTag === "textarea" || activeTag === "select") return;

      switch (event.key) {
        case "Escape":
          onDeselect();
          fitViewport();
          break;
        case "+":
        case "=":
          zoomIn();
          break;
        case "-":
          zoomOut();
          break;
        case "ArrowUp":
          panBy(0, KEYBOARD_PAN_STEP);
          break;
        case "ArrowDown":
          panBy(0, -KEYBOARD_PAN_STEP);
          break;
        case "ArrowLeft":
          panBy(KEYBOARD_PAN_STEP, 0);
          break;
        case "ArrowRight":
          panBy(-KEYBOARD_PAN_STEP, 0);
          break;
        case "/":
          if (onSearchFocus) {
            event.preventDefault();
            onSearchFocus();
          }
          break;
        default:
          return;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [containerRef, fitViewport, onDeselect, onSearchFocus, panBy, zoomIn, zoomOut]);

  return {
    viewport,
    hoveredId,
    isPanning,
    size,
    setHoveredId,
    fitViewport,
    zoomIn,
    zoomOut,
    panBy,
    handleBackgroundPointerDown,
    handleBackgroundPointerMove,
    handleBackgroundPointerUp,
  };
}
