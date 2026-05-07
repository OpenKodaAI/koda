// Pure helpers for detecting `/` and `@` trigger tokens in the composer
// textarea. The composer wires these into a state hook that tracks caret
// position and re-runs the detector on each onChange / onSelect event.
//
//   - The slash trigger fires only at start-of-text or after whitespace,
//     so URLs (https) and Markdown end-of-block markers never trigger.
//   - The at-sign trigger follows the same rule, so emails like
//     ryan@gmail.com never trigger (the @ is preceded by a letter).
//
// The returned range is [start, end] where start is the index of the
// trigger character and end is the caret position (exclusive). The query
// is the substring after the trigger character up to the caret.

export type TriggerChar = "/" | "@";

export interface TriggerMatch {
  /** Index of the trigger character in the source text. */
  start: number;
  /** Caret position (exclusive end of the active token). */
  end: number;
  /** Text after the trigger up to the caret. */
  query: string;
}

const WHITESPACE = /\s/;

function isBoundary(text: string, index: number): boolean {
  if (index <= 0) return true;
  return WHITESPACE.test(text.charAt(index - 1));
}

/**
 * Inspect the text immediately preceding the caret and return a TriggerMatch
 * if a clean trigger token is active. Returns null otherwise.
 *
 * The "active" token must:
 *   1. Start with the trigger char preceded by whitespace or start-of-text.
 *   2. Contain no whitespace after the trigger char (so the menu closes the
 *      moment the user types a space).
 *   3. End at the caret (we never autocomplete in the middle of a word).
 */
export function detectTrigger(
  text: string,
  caret: number,
  trigger: TriggerChar,
): TriggerMatch | null {
  if (caret < 0 || caret > text.length) return null;

  // Walk back from the caret looking for the most recent trigger char that
  // satisfies the boundary rule and has no whitespace between it and the caret.
  for (let i = caret - 1; i >= 0; i -= 1) {
    const ch = text.charAt(i);
    if (ch === trigger && isBoundary(text, i)) {
      const query = text.slice(i + 1, caret);
      if (WHITESPACE.test(query)) return null;
      return { start: i, end: caret, query };
    }
    if (WHITESPACE.test(ch)) {
      // Hit a whitespace before finding the trigger — no active token.
      return null;
    }
  }

  return null;
}

/**
 * Replace the trigger range with `replacement`. Returns the new text and the
 * caret position immediately after the inserted replacement.
 */
export function applyReplacement(
  text: string,
  match: TriggerMatch,
  replacement: string,
): { text: string; caret: number } {
  const before = text.slice(0, match.start);
  const after = text.slice(match.end);
  const next = `${before}${replacement}${after}`;
  return { text: next, caret: before.length + replacement.length };
}

/**
 * Clear a trigger range entirely (for `execute` commands that don't insert
 * any literal text). Returns the new text and the caret position at the
 * boundary where the trigger used to start.
 */
export function clearTrigger(
  text: string,
  match: TriggerMatch,
): { text: string; caret: number } {
  return applyReplacement(text, match, "");
}
