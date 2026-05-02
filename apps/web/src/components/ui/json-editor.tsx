"use client";

/**
 * JsonEditor — minimal JSON editor with token-level syntax highlighting and
 * inline parse error reporting. No external dependencies (no codemirror /
 * monaco / prism), just a regex tokenizer drawn into a `<pre>` underneath a
 * transparent `<textarea>`. Caret, selection and scrolling stay in the
 * textarea so it behaves like a normal input.
 *
 * Usage:
 *
 *   <JsonEditor
 *     value={raw}
 *     onChange={setRaw}
 *     placeholder="{ \"foo\": 1 }"
 *     onValidate={(ok, err) => ...}
 *   />
 */

import * as React from "react";
import { cn } from "@/lib/utils";

export type JsonValidation = {
  valid: boolean;
  error: string | null;
  /** 1-based line number when error position is decodable. */
  line?: number;
  /** 1-based column number when error position is decodable. */
  column?: number;
};

export interface JsonEditorProps {
  value: string;
  onChange: (next: string) => void;
  onValidate?: (status: JsonValidation) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
  readOnly?: boolean;
  /** Show validation banner inline; defaults to true. */
  showValidation?: boolean;
  ariaLabel?: string;
}

/* ------------------------------------------------------------------ */
/*  Tokenizer                                                          */
/* ------------------------------------------------------------------ */

type TokenKind = "key" | "string" | "number" | "bool" | "null" | "punct" | "ws";

type Token = { kind: TokenKind; text: string };

// Regexes, in order of preference. The tokenizer scans the source greedily,
// preferring strings (which can contain anything) over identifiers.
const STRING_RE = /^"(?:[^"\\]|\\.)*"/;
const NUMBER_RE = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/;
const KEYWORD_RE = /^(?:true|false|null)\b/;
const PUNCT_RE = /^[\{\}\[\],:]/;
const WS_RE = /^[\s]+/;

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let cursor = 0;
  while (cursor < source.length) {
    const remainder = source.slice(cursor);

    const stringMatch = remainder.match(STRING_RE);
    if (stringMatch) {
      const text = stringMatch[0];
      cursor += text.length;
      // Determine if this string is in a key position: next non-ws char is ':'.
      let probe = cursor;
      while (probe < source.length && /\s/.test(source[probe]!)) probe += 1;
      const isKey = source[probe] === ":";
      tokens.push({ kind: isKey ? "key" : "string", text });
      continue;
    }

    const numberMatch = remainder.match(NUMBER_RE);
    if (numberMatch) {
      const text = numberMatch[0];
      cursor += text.length;
      tokens.push({ kind: "number", text });
      continue;
    }

    const keywordMatch = remainder.match(KEYWORD_RE);
    if (keywordMatch) {
      const text = keywordMatch[0];
      cursor += text.length;
      tokens.push({ kind: text === "null" ? "null" : "bool", text });
      continue;
    }

    const punctMatch = remainder.match(PUNCT_RE);
    if (punctMatch) {
      const text = punctMatch[0];
      cursor += text.length;
      tokens.push({ kind: "punct", text });
      continue;
    }

    const wsMatch = remainder.match(WS_RE);
    if (wsMatch) {
      const text = wsMatch[0];
      cursor += text.length;
      tokens.push({ kind: "ws", text });
      continue;
    }

    // Unknown char — emit one literal so highlighting keeps in sync with
    // the textarea's character positions even when the JSON is malformed.
    tokens.push({ kind: "ws", text: source[cursor]! });
    cursor += 1;
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  Token color resolution                                             */
/* ------------------------------------------------------------------ */

// Soft IDE-style palette tuned for the Koda dark canvas. Bright enough to
// be legible against `--panel-soft`, muted enough to never compete with
// the warm CTA accent. Tokens follow the conventional shape: keys blue,
// strings yellow, numbers green, literals violet.
const TOKEN_CLASS: Record<TokenKind, string> = {
  key: "text-[var(--json-key)] font-medium",
  string: "text-[var(--json-string)]",
  number: "text-[var(--json-number)]",
  bool: "text-[var(--json-literal)] italic",
  null: "text-[var(--json-literal)] italic",
  punct: "text-[var(--json-punct)]",
  ws: "",
};

/* ------------------------------------------------------------------ */
/*  Validation                                                         */
/* ------------------------------------------------------------------ */

function validateJson(source: string): JsonValidation {
  const trimmed = source.trim();
  if (!trimmed) return { valid: true, error: null };
  try {
    JSON.parse(trimmed);
    return { valid: true, error: null };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // V8 messages look like: "Unexpected token a in JSON at position 12"
    // or "Expected property name or '}' in JSON at position 5 (line 1
    // column 6)". We extract position to compute line/column ourselves.
    const positionMatch = message.match(/position (\d+)/);
    if (positionMatch) {
      const pos = Number(positionMatch[1]);
      const before = source.slice(0, pos);
      const lines = before.split("\n");
      return {
        valid: false,
        error: message,
        line: lines.length,
        column: lines[lines.length - 1]!.length + 1,
      };
    }
    return { valid: false, error: message };
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function JsonEditor({
  value,
  onChange,
  onValidate,
  placeholder,
  rows = 12,
  className,
  readOnly = false,
  showValidation = true,
  ariaLabel,
}: JsonEditorProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const preRef = React.useRef<HTMLPreElement>(null);
  const validation = React.useMemo(() => validateJson(value), [value]);

  React.useEffect(() => {
    onValidate?.(validation);
  }, [validation, onValidate]);

  const tokens = React.useMemo(() => tokenize(value), [value]);

  // Mirror textarea scroll into the highlight layer so they stay aligned
  // when the textarea overflows.
  const handleScroll = React.useCallback(() => {
    if (!textareaRef.current || !preRef.current) return;
    preRef.current.scrollTop = textareaRef.current.scrollTop;
    preRef.current.scrollLeft = textareaRef.current.scrollLeft;
  }, []);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div
        className={cn(
          "relative w-full overflow-hidden rounded-[var(--radius-input)] border bg-[var(--panel-soft)] font-mono text-xs leading-[1.5]",
          "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "border-[var(--border-subtle)] hover:border-[var(--border-strong)]",
          "focus-within:border-[var(--accent)]",
          !validation.valid && "border-[var(--tone-danger-border)] focus-within:border-[var(--tone-danger-border)]",
        )}
      >
        {/* Highlight layer */}
        <pre
          ref={preRef}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 m-0 overflow-auto whitespace-pre-wrap break-words px-3 py-2 font-mono text-xs leading-[1.5]"
        >
          {tokens.length === 0 && placeholder ? (
            <span className="text-[var(--text-quaternary)]">{placeholder}</span>
          ) : (
            tokens.map((token, idx) => (
              <span key={idx} className={TOKEN_CLASS[token.kind]}>
                {token.text}
              </span>
            ))
          )}
          {/* trailing newline so the textarea height matches when value ends with \n */}
          {"\n"}
        </pre>

        {/* Transparent textarea — owns caret, selection, and input */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onScroll={handleScroll}
          rows={rows}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          aria-label={ariaLabel}
          aria-invalid={!validation.valid}
          readOnly={readOnly}
          className={cn(
            "relative block w-full resize-y bg-transparent px-3 py-2 font-mono text-xs leading-[1.5] text-transparent caret-[var(--text-primary)] outline-none",
            // Selection still readable on the highlight layer below
            "selection:bg-[var(--accent-muted)] selection:text-[var(--text-primary)]",
            "placeholder:text-[var(--text-quaternary)]",
            readOnly && "cursor-default",
          )}
          style={{ minHeight: `${rows * 1.5}rem` }}
        />
      </div>

      {showValidation && !validation.valid ? (
        <p className="text-[11px] font-medium text-[var(--tone-danger-dot)]">
          {validation.line && validation.column
            ? `${validation.error} (linha ${validation.line}, col ${validation.column})`
            : validation.error}
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Templates                                                          */
/* ------------------------------------------------------------------ */

/**
 * Empty Claude Desktop-style template — single placeholder server, no
 * sample servers polluting the user's view.
 */
export const EMPTY_MCP_SERVERS_TEMPLATE = `{
  "mcpServers": {
    "": {
      "command": "",
      "args": [],
      "env": {}
    }
  }
}
`;
