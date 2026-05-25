import { z } from "zod";

const DANGEROUS_PATTERN =
  /<script[\s>/][\s\S]*?(<\/script\s*>|$)|javascript\s*:|data\s*:|vbscript\s*:|on\w+\s*=/gi;

function stripDangerousPatterns(value: string): string {
  return value.replace(DANGEROUS_PATTERN, "");
}

/** Trimmed, max-length, dangerous HTML/JS stripped. Use for display names, descriptions. */
export function safeText(max: number) {
  return z
    .string()
    .trim()
    .max(max)
    .transform(stripDangerousPatterns);
}

/** Trimmed, max-length, alphanumeric + : _ - only. Use for identifiers. */
export function safeIdentifier(max: number) {
  return z
    .string()
    .trim()
    .min(1, "Identifier is required.")
    .max(max)
    .regex(/^[A-Za-z0-9:_-]+$/, "Only letters, numbers, colons, underscores and hyphens allowed.");
}

/** Hex color: #RRGGBB format. */
export function hexColor() {
  return z
    .string()
    .trim()
    .regex(/^#[0-9a-fA-F]{6}$/, "Must be a hex color (#RRGGBB).");
}

/** Trimmed, max-length, no HTML stripping. Use for long-form content (prompts, markdown). */
export function safeContent(max: number) {
  return z.string().trim().max(max);
}

/** RGB string like "255, 90, 90". */
export function rgbString() {
  return z
    .string()
    .trim()
    .regex(
      /^\d{1,3},\s*\d{1,3},\s*\d{1,3}$/,
      "Must be an RGB string (e.g. '255, 90, 90').",
    );
}

