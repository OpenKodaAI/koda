"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import { MAX_AGENT_ORB_COLORS } from "@/components/ui/agent-orb-constants";
import { Orb, type AgentState, type OrbColorPair } from "@/components/ui/orb";
import { useInViewport } from "@/hooks/use-in-viewport";
import { cn } from "@/lib/utils";

export type { AgentState };
export { MAX_AGENT_ORB_COLORS };

interface AgentGlyphProps {
  agentId: string;
  color: string;
  /**
   * Multi-agent palette. Dense selections are capped to a representative
   * palette before they reach WebGL, keeping the selector orb readable and
   * cheap to mount. Falls back to the single `color` prop when omitted.
   */
  colors?: string[];
  className?: string;
  active?: boolean;
  state?: AgentState;
  variant?: "card" | "list";
  shape?: "orb" | "swatch";
}

const FALLBACK_COLOR = "#A7ADB4";
const ORB_VIEWPORT_ROOT_MARGIN = "160px 0px";
const ORB_MOUNT_STAGGER_MS = 160;

export function getAgentOrbColor(color: string): string {
  return color || FALLBACK_COLOR;
}

export function deriveAgentState(input: {
  activeTasks: number;
  featuredStatus: string | null;
  dbExists?: boolean;
}): AgentState {
  if (input.dbExists === false) return null;
  if ((input.activeTasks ?? 0) <= 0) return null;
  switch (input.featuredStatus) {
    case "running":
    case "retrying":
      return "thinking";
    case "queued":
      return "listening";
    default:
      return null;
  }
}

// Hashes the agent id into a deterministic 32-bit seed so each agent gets a
// stable orb shape across mounts (without pinning the random orb to a hard-
// coded constant).
function hashAgentId(id: string): number {
  let hash = 2166136261 >>> 0;
  for (let i = 0; i < id.length; i += 1) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash >>> 0;
}

// Convert a single hex color into the {light, dark} tonal pair the orb
// shader expects. Mirrors the default (#CADCFC / #A0B9D1) — a light variant
// brighter than the agent color and a dark variant about a quarter darker.
function tonalPair(color: string): OrbColorPair {
  const hex = parseHex(getAgentOrbColor(color));
  if (!hex) {
    return { light: "#CADCFC", dark: "#A0B9D1" };
  }
  const [h, s, l] = rgbToHsl(hex);
  const light = hslToHex(h, clamp01(s * 0.95), clamp01(Math.max(l, 0.55) + 0.1));
  const dark = hslToHex(h, clamp01(s * 0.85), clamp01(Math.max(l, 0.4) - 0.15));
  return { light, dark };
}

function clamp01(n: number): number {
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function parseHex(input: string): [number, number, number] | null {
  const value = input.trim().replace(/^#/, "");
  if (value.length === 3) {
    const r = parseInt(value[0] + value[0], 16);
    const g = parseInt(value[1] + value[1], 16);
    const b = parseInt(value[2] + value[2], 16);
    if ([r, g, b].some(Number.isNaN)) return null;
    return [r, g, b];
  }
  if (value.length === 6) {
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    if ([r, g, b].some(Number.isNaN)) return null;
    return [r, g, b];
  }
  return null;
}

function rgbToHsl([r, g, b]: [number, number, number]): [number, number, number] {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) {
    return [0, 0, l];
  }
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  switch (max) {
    case rn:
      h = (gn - bn) / d + (gn < bn ? 6 : 0);
      break;
    case gn:
      h = (bn - rn) / d + 2;
      break;
    default:
      h = (rn - gn) / d + 4;
  }
  return [h / 6, s, l];
}

function hslToHex(h: number, s: number, l: number): string {
  const hue2rgb = (p: number, q: number, t: number) => {
    let tt = t;
    if (tt < 0) tt += 1;
    if (tt > 1) tt -= 1;
    if (tt < 1 / 6) return p + (q - p) * 6 * tt;
    if (tt < 1 / 2) return q;
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
    return p;
  };
  let r: number;
  let g: number;
  let b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }
  const toHex = (channel: number) =>
    Math.round(clamp01(channel) * 255)
      .toString(16)
      .padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function useDeferredOrbMount(enabled: boolean, seed: number): boolean {
  const [readySeed, setReadySeed] = useState<number | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timeout = window.setTimeout(
      () => setReadySeed(seed),
      seed % ORB_MOUNT_STAGGER_MS,
    );
    return () => window.clearTimeout(timeout);
  }, [enabled, seed]);

  return enabled && readySeed === seed;
}

export function AgentGlyph({
  agentId,
  color,
  colors,
  className,
  active = false,
  state = null,
  variant = "card",
  shape = "orb",
}: AgentGlyphProps) {
  const [forceStaticGlyph] = useState(
    () => typeof navigator !== "undefined" && Boolean(navigator.webdriver),
  );
  const orbColor = getAgentOrbColor(color);
  const isListVariant = variant === "list";
  const sizeClass = isListVariant ? "h-8 w-8" : "h-12 w-12";

  const seed = useMemo(() => hashAgentId(agentId || orbColor), [agentId, orbColor]);
  const primaryPair = useMemo(() => tonalPair(orbColor), [orbColor]);
  const palette = useMemo<OrbColorPair[] | undefined>(() => {
    if (!colors || colors.length <= 1) return undefined;
    return colors
      .slice(0, MAX_AGENT_ORB_COLORS)
      .map((c) => tonalPair(c || FALLBACK_COLOR));
  }, [colors]);

  const orbStyle = {
    "--agent-orb-color": orbColor,
  } as CSSProperties;

  // Lazy-mount the WebGL Canvas only when the host element is in (or near)
  // the viewport, so dense lists don't simultaneously hold more WebGL contexts
  // than the browser allows (~16 in Chrome). Called unconditionally — the
  // swatch branch ignores `ref` and `inView`.
  const { ref, inView } = useInViewport<HTMLSpanElement>({
    rootMargin: ORB_VIEWPORT_ROOT_MARGIN,
  });
  const shouldMountOrb = useDeferredOrbMount(shape === "orb" && inView, seed);

  if (shape === "swatch" || forceStaticGlyph) {
    return (
      <span
        className={cn(
          "agent-swatch",
          sizeClass,
          active && "agent-swatch--active",
          className,
        )}
        style={{ "--agent-orb-color": orbColor } as CSSProperties}
        aria-hidden="true"
      >
        <span className="agent-swatch__halo" />
        <span className="agent-swatch__base" />
        <span className="agent-swatch__swirl" />
        <span className="agent-swatch__shine" />
        <span className="agent-swatch__grain" />
      </span>
    );
  }

  return (
    <span
      ref={ref}
      className={cn(
        "agent-orb",
        sizeClass,
        active && "agent-orb--active",
        className,
      )}
      style={orbStyle}
      aria-hidden="true"
    >
      {shouldMountOrb ? (
        <Orb
          colors={[primaryPair.light, primaryPair.dark]}
          agentColors={palette}
          agentState={state}
          seed={seed}
          className="absolute inset-0"
        />
      ) : null}
    </span>
  );
}
