import type { CSSProperties } from "react";

export type SemanticTone =
  | "neutral"
  | "success"
  | "info"
  | "warning"
  | "danger"
  | "retry";

interface SemanticToneVars {
  bg: string;
  bgStrong: string;
  border: string;
  text: string;
  muted: string;
  dot: string;
}

const tone = (name: string): SemanticToneVars => ({
  bg: `var(--tone-${name}-bg)`,
  bgStrong: `var(--tone-${name}-bg-strong)`,
  border: `var(--tone-${name}-border)`,
  text: `var(--tone-${name}-text)`,
  muted: `var(--tone-${name}-muted)`,
  dot: `var(--tone-${name}-dot)`,
});

export const SEMANTIC_TONES: Record<SemanticTone, SemanticToneVars> = {
  neutral: tone("neutral"),
  success: tone("success"),
  info: tone("info"),
  warning: tone("warning"),
  danger: tone("danger"),
  retry: tone("retry"),
};

export function getSemanticTone(status: string): SemanticTone {
  if (status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "queued") return "warning";
  if (status === "failed") return "danger";
  if (status === "retrying") return "retry";
  return "neutral";
}

export function getSemanticVars(toneName: SemanticTone): SemanticToneVars {
  return SEMANTIC_TONES[toneName];
}

export function getSemanticStyle(toneName: SemanticTone): CSSProperties {
  const vars = getSemanticVars(toneName);
  return {
    backgroundColor: vars.bg,
    borderColor: vars.border,
    color: vars.text,
  };
}

export function getSemanticStrongStyle(toneName: SemanticTone): CSSProperties {
  const vars = getSemanticVars(toneName);
  return {
    backgroundColor: vars.bgStrong,
    borderColor: vars.border,
    color: vars.text,
  };
}

export function getSemanticIconStyle(toneName: SemanticTone): CSSProperties {
  const vars = getSemanticVars(toneName);
  return {
    backgroundColor: vars.bgStrong,
    borderColor: vars.border,
    color: vars.text,
  };
}

export function getSemanticDotStyle(toneName: SemanticTone): CSSProperties {
  return {
    backgroundColor: getSemanticVars(toneName).dot,
  };
}

export function getSemanticTextStyle(
  toneName: SemanticTone,
  muted = false
): CSSProperties {
  const vars = getSemanticVars(toneName);
  return {
    color: muted ? vars.muted : vars.text,
  };
}
