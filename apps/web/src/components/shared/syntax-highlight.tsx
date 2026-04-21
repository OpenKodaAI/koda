"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Language detection                                                 */
/* ------------------------------------------------------------------ */

export type SyntaxLang = "json" | "sql" | "shell" | "diff" | "python" | "typescript" | "yaml" | "html" | "css" | "plain";

/* ------------------------------------------------------------------ */
/*  Extension → language detection                                     */
/* ------------------------------------------------------------------ */

const EXT_TO_LANG: Record<string, SyntaxLang> = {
  ".json": "json",
  ".jsonl": "json",
  ".sql": "sql",
  ".sh": "shell",
  ".bash": "shell",
  ".zsh": "shell",
  ".diff": "diff",
  ".patch": "diff",
  ".py": "python",
  ".ts": "typescript",
  ".tsx": "typescript",
  ".js": "typescript",
  ".jsx": "typescript",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".html": "html",
  ".htm": "html",
  ".css": "css",
  ".scss": "css",
};

const EXT_TO_LABEL: Record<string, string> = {
  ".ts": "TypeScript",
  ".tsx": "TypeScript (JSX)",
  ".js": "JavaScript",
  ".jsx": "JavaScript (JSX)",
  ".json": "JSON",
  ".jsonl": "JSON Lines",
  ".py": "Python",
  ".rb": "Ruby",
  ".rs": "Rust",
  ".go": "Go",
  ".java": "Java",
  ".kt": "Kotlin",
  ".swift": "Swift",
  ".c": "C",
  ".cpp": "C++",
  ".h": "C Header",
  ".hpp": "C++ Header",
  ".cs": "C#",
  ".sql": "SQL",
  ".sh": "Shell",
  ".bash": "Bash",
  ".zsh": "Zsh",
  ".diff": "Diff",
  ".patch": "Patch",
  ".md": "Markdown",
  ".mdx": "MDX",
  ".yaml": "YAML",
  ".yml": "YAML",
  ".toml": "TOML",
  ".xml": "XML",
  ".html": "HTML",
  ".css": "CSS",
  ".scss": "SCSS",
  ".less": "Less",
  ".lua": "Lua",
  ".php": "PHP",
  ".r": "R",
  ".pl": "Perl",
  ".ex": "Elixir",
  ".exs": "Elixir Script",
  ".erl": "Erlang",
  ".hs": "Haskell",
  ".ml": "OCaml",
  ".scala": "Scala",
  ".clj": "Clojure",
  ".vue": "Vue",
  ".svelte": "Svelte",
  ".tf": "Terraform",
  ".dockerfile": "Dockerfile",
  ".env": "Environment",
  ".ini": "INI",
  ".conf": "Config",
  ".cfg": "Config",
  ".txt": "Text",
  ".log": "Log",
  ".csv": "CSV",
  ".tsv": "TSV",
};

function getExtension(filePath: string): string {
  const base = filePath.split("/").pop() || "";
  if (base.toLowerCase() === "dockerfile") return ".dockerfile";
  const dotIndex = base.lastIndexOf(".");
  return dotIndex >= 0 ? base.slice(dotIndex).toLowerCase() : "";
}

export function detectLangFromPath(filePath: string): SyntaxLang {
  const ext = getExtension(filePath);
  return EXT_TO_LANG[ext] ?? "plain";
}

export function getLanguageLabel(filePath: string): string {
  const ext = getExtension(filePath);
  return EXT_TO_LABEL[ext] ?? (ext ? ext.slice(1).toUpperCase() : "Plain Text");
}

const SQL_KW =
  /\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|ON|AND|OR|NOT|IN|EXISTS|BETWEEN|LIKE|IS|NULL|AS|ORDER|BY|GROUP|HAVING|LIMIT|OFFSET|UNION|ALL|DISTINCT|SET|INTO|VALUES|TABLE|INDEX|VIEW|WITH|CASE|WHEN|THEN|ELSE|END|COUNT|SUM|AVG|MIN|MAX|COALESCE|CAST|RETURNING|DESC|ASC|PRIMARY|KEY|FOREIGN|REFERENCES|CONSTRAINT|DEFAULT|CHECK|UNIQUE|IF|BEGIN|COMMIT|ROLLBACK)\b/i;

export function detectLang(content: string): SyntaxLang {
  const trimmed = content.trim();

  // JSON: starts with { or [
  if (/^[\[{]/.test(trimmed)) {
    try {
      JSON.parse(trimmed);
      return "json";
    } catch {
      // might still be JSON-like but malformed — check for typical patterns
      if (/^{[\s\S]*"[\w]+"[\s]*:/.test(trimmed)) return "json";
    }
  }

  // Diff: starts with diff/--- /+++ or has diff-like hunks
  if (
    /^(diff\s|---\s|@@\s)/.test(trimmed) ||
    /\n@@\s/.test(trimmed) ||
    (/^\+{3}\s/.test(trimmed) && /\n-{3}\s/.test(trimmed))
  ) {
    return "diff";
  }

  // SQL: has multiple SQL keywords
  const sqlMatches = trimmed.match(new RegExp(SQL_KW.source, "gi"));
  if (sqlMatches && sqlMatches.length >= 2) return "sql";

  // Python: has def/class/import patterns
  if (/^(def |class |import |from \w+ import )/.test(trimmed)) return "python";

  // YAML: has key: value patterns on multiple lines
  if (/^[\w.-]+:\s+\S/.test(trimmed) && /\n[\w.-]+:\s+\S/.test(trimmed)) return "yaml";

  // Shell: starts with $ or common CLI patterns
  if (/^(\$\s|#!\/)/.test(trimmed) || /^[a-z_/][a-z0-9_/.-]*\s+-/.test(trimmed)) {
    return "shell";
  }

  return "plain";
}

/* ------------------------------------------------------------------ */
/*  Token types                                                        */
/* ------------------------------------------------------------------ */

interface Token {
  type:
    | "plain"
    | "key"
    | "string"
    | "number"
    | "boolean"
    | "null"
    | "bracket"
    | "keyword"
    | "function"
    | "operator"
    | "comment"
    | "flag"
    | "command"
    | "diff-add"
    | "diff-remove"
    | "diff-hunk"
    | "diff-header";
  text: string;
}

/* ------------------------------------------------------------------ */
/*  JSON tokenizer                                                     */
/* ------------------------------------------------------------------ */

function tokenizeJson(code: string): Token[] {
  const tokens: Token[] = [];
  // Match: strings, numbers, booleans, null, brackets, commas/colons
  const rx =
    /("(?:[^"\\]|\\.)*")\s*(:)|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b|(true|false)\b|(null)\b|([{}\[\]])|(\S)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = rx.exec(code)) !== null) {
    // plain text gap
    if (match.index > lastIndex) {
      tokens.push({ type: "plain", text: code.slice(lastIndex, match.index) });
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null) {
      // key: value
      tokens.push({ type: "key", text: match[1] });
      tokens.push({ type: "plain", text: ": ".slice(0, match[0].length - match[1].length) });
    } else if (match[3] != null) {
      tokens.push({ type: "string", text: match[3] });
    } else if (match[4] != null) {
      tokens.push({ type: "number", text: match[4] });
    } else if (match[5] != null) {
      tokens.push({ type: "boolean", text: match[5] });
    } else if (match[6] != null) {
      tokens.push({ type: "null", text: match[6] });
    } else if (match[7] != null) {
      tokens.push({ type: "bracket", text: match[7] });
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  SQL tokenizer                                                      */
/* ------------------------------------------------------------------ */

const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER",
  "DROP", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS", "ON", "AND",
  "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "IS", "NULL", "AS",
  "ORDER", "BY", "GROUP", "HAVING", "LIMIT", "OFFSET", "UNION", "ALL",
  "DISTINCT", "SET", "INTO", "VALUES", "TABLE", "INDEX", "VIEW", "WITH",
  "CASE", "WHEN", "THEN", "ELSE", "END", "RETURNING", "DESC", "ASC",
  "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "CONSTRAINT", "DEFAULT",
  "CHECK", "UNIQUE", "IF", "BEGIN", "COMMIT", "ROLLBACK", "CASCADE",
  "TRUE", "FALSE",
]);

const SQL_FNS = new Set([
  "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "CAST", "NOW",
  "EXTRACT", "LOWER", "UPPER", "LENGTH", "SUBSTRING", "TRIM", "CONCAT",
  "ROW_NUMBER", "RANK", "DENSE_RANK", "OVER", "PARTITION",
  "DATE_TRUNC", "TO_CHAR", "TO_DATE", "TO_TIMESTAMP", "ARRAY_AGG",
  "STRING_AGG", "JSON_AGG", "JSONB_AGG", "JSON_BUILD_OBJECT",
  "JSONB_BUILD_OBJECT",
]);

function tokenizeSql(code: string): Token[] {
  const tokens: Token[] = [];
  const rx =
    /('(?:[^'\\]|\\.)*')|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)\b|(--[^\n]*)|(\b[A-Za-z_]\w*\b)|([(),.;*=<>!]+)|(\S)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = rx.exec(code)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "plain", text: code.slice(lastIndex, match.index) });
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null || match[2] != null) {
      tokens.push({ type: "string", text: match[0] });
    } else if (match[3] != null) {
      tokens.push({ type: "number", text: match[3] });
    } else if (match[4] != null) {
      tokens.push({ type: "comment", text: match[4] });
    } else if (match[5] != null) {
      const upper = match[5].toUpperCase();
      if (SQL_KEYWORDS.has(upper)) {
        tokens.push({ type: "keyword", text: match[5] });
      } else if (SQL_FNS.has(upper)) {
        tokens.push({ type: "function", text: match[5] });
      } else {
        tokens.push({ type: "plain", text: match[5] });
      }
    } else if (match[6] != null) {
      tokens.push({ type: "operator", text: match[6] });
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  Shell tokenizer                                                    */
/* ------------------------------------------------------------------ */

function tokenizeShell(code: string): Token[] {
  const tokens: Token[] = [];
  const rx =
    /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(#[^\n]*)|(--?[\w][\w-]*)|(\$[\w{][^\s}]*}?)|(\|{1,2}|&&|;|>>?|<)|(\b\d+\b)|(\S+)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;
  let isFirstWord = true;

  while ((match = rx.exec(code)) !== null) {
    if (match.index > lastIndex) {
      const gap = code.slice(lastIndex, match.index);
      tokens.push({ type: "plain", text: gap });
      if (gap.includes("\n")) isFirstWord = true;
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null) {
      tokens.push({ type: "string", text: match[1] });
    } else if (match[2] != null) {
      tokens.push({ type: "comment", text: match[2] });
    } else if (match[3] != null) {
      tokens.push({ type: "flag", text: match[3] });
    } else if (match[4] != null) {
      tokens.push({ type: "keyword", text: match[4] });
    } else if (match[5] != null) {
      tokens.push({ type: "operator", text: match[5] });
    } else if (match[6] != null) {
      tokens.push({ type: "number", text: match[6] });
    } else if (match[7] != null) {
      if (isFirstWord || match[7] === "$") {
        tokens.push({ type: "command", text: match[7] });
      } else {
        tokens.push({ type: "plain", text: match[7] });
      }
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
    isFirstWord = false;
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  Diff tokenizer (line-based)                                        */
/* ------------------------------------------------------------------ */

function tokenizeDiff(code: string): Token[] {
  const tokens: Token[] = [];
  const lines = code.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (i > 0) tokens.push({ type: "plain", text: "\n" });

    if (line.startsWith("diff ") || line.startsWith("index ")) {
      tokens.push({ type: "diff-header", text: line });
    } else if (line.startsWith("@@")) {
      tokens.push({ type: "diff-hunk", text: line });
    } else if (line.startsWith("---") || line.startsWith("+++")) {
      tokens.push({ type: "diff-header", text: line });
    } else if (line.startsWith("+")) {
      tokens.push({ type: "diff-add", text: line });
    } else if (line.startsWith("-")) {
      tokens.push({ type: "diff-remove", text: line });
    } else {
      tokens.push({ type: "plain", text: line });
    }
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  Python tokenizer                                                   */
/* ------------------------------------------------------------------ */

const PY_KEYWORDS = new Set([
  "def", "class", "import", "from", "return", "if", "elif", "else", "for",
  "while", "try", "except", "finally", "with", "as", "yield", "lambda",
  "pass", "break", "continue", "raise", "in", "not", "and", "or", "is",
  "None", "True", "False", "self", "async", "await",
]);

const PY_BUILTINS = new Set([
  "print", "len", "range", "list", "dict", "str", "int", "float", "type",
  "isinstance", "enumerate", "zip", "map", "filter", "open", "super",
]);

function tokenizePython(code: string): Token[] {
  const tokens: Token[] = [];
  const rx =
    /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(#[^\n]*)|(@\w+)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b|(\b[A-Za-z_]\w*\b)|([()[\]{},.:;=+\-*/<>!&|^~%]+)|(\S)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = rx.exec(code)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "plain", text: code.slice(lastIndex, match.index) });
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null) {
      tokens.push({ type: "string", text: match[1] });
    } else if (match[2] != null) {
      tokens.push({ type: "comment", text: match[2] });
    } else if (match[3] != null) {
      tokens.push({ type: "command", text: match[3] });
    } else if (match[4] != null) {
      tokens.push({ type: "number", text: match[4] });
    } else if (match[5] != null) {
      if (PY_KEYWORDS.has(match[5])) {
        tokens.push({ type: "keyword", text: match[5] });
      } else if (PY_BUILTINS.has(match[5])) {
        tokens.push({ type: "function", text: match[5] });
      } else {
        tokens.push({ type: "plain", text: match[5] });
      }
    } else if (match[6] != null) {
      tokens.push({ type: "operator", text: match[6] });
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  TypeScript tokenizer                                               */
/* ------------------------------------------------------------------ */

const TS_KEYWORDS = new Set([
  "const", "let", "var", "function", "class", "interface", "type", "enum",
  "import", "export", "from", "return", "if", "else", "for", "while",
  "switch", "case", "break", "continue", "try", "catch", "finally", "throw",
  "new", "typeof", "instanceof", "void", "null", "undefined", "true", "false",
  "this", "async", "await", "of", "in", "extends", "implements", "readonly",
  "abstract", "static", "as", "satisfies",
]);

function tokenizeTypeScript(code: string): Token[] {
  const tokens: Token[] = [];
  const rx =
    /(`(?:[^`\\]|\\.)*`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\/\/[^\n]*|\/\*[\s\S]*?\*\/)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b|(\b[A-Za-z_$]\w*\b)|([()[\]{},.:;=+\-*/<>!&|^~%?@]+)|(\S)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = rx.exec(code)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "plain", text: code.slice(lastIndex, match.index) });
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null) {
      tokens.push({ type: "string", text: match[1] });
    } else if (match[2] != null) {
      tokens.push({ type: "comment", text: match[2] });
    } else if (match[3] != null) {
      tokens.push({ type: "number", text: match[3] });
    } else if (match[4] != null) {
      if (TS_KEYWORDS.has(match[4])) {
        tokens.push({ type: "keyword", text: match[4] });
      } else {
        tokens.push({ type: "plain", text: match[4] });
      }
    } else if (match[5] != null) {
      tokens.push({ type: "operator", text: match[5] });
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  YAML tokenizer (line-based)                                        */
/* ------------------------------------------------------------------ */

function tokenizeYaml(code: string): Token[] {
  const tokens: Token[] = [];
  const lines = code.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (i > 0) tokens.push({ type: "plain", text: "\n" });

    // Comment line
    if (/^\s*#/.test(line)) {
      tokens.push({ type: "comment", text: line });
      continue;
    }

    // Anchors & aliases
    if (/^\s*[&*]\w/.test(line)) {
      const m = line.match(/^(\s*)([&*]\w+)(.*)/);
      if (m) {
        if (m[1]) tokens.push({ type: "plain", text: m[1] });
        tokens.push({ type: "keyword", text: m[2] });
        if (m[3]) tokens.push({ type: "plain", text: m[3] });
        continue;
      }
    }

    // key: value
    const kvMatch = line.match(/^(\s*)([\w.-]+[^:]*)(:)([ ]+)(.*)/);
    if (kvMatch) {
      if (kvMatch[1]) tokens.push({ type: "plain", text: kvMatch[1] });
      tokens.push({ type: "key", text: kvMatch[2] });
      tokens.push({ type: "operator", text: kvMatch[3] });
      tokens.push({ type: "plain", text: kvMatch[4] });
      const val = kvMatch[5];
      // Inline comment
      const commentIdx = val.indexOf(" #");
      const valPart = commentIdx >= 0 ? val.slice(0, commentIdx) : val;
      const commentPart = commentIdx >= 0 ? val.slice(commentIdx) : "";
      if (/^(true|false|yes|no|on|off)$/i.test(valPart)) {
        tokens.push({ type: "boolean", text: valPart });
      } else if (/^-?\d+(\.\d+)?$/.test(valPart)) {
        tokens.push({ type: "number", text: valPart });
      } else if (/^(["']).*\1$/.test(valPart)) {
        tokens.push({ type: "string", text: valPart });
      } else if (valPart === "null" || valPart === "~") {
        tokens.push({ type: "null", text: valPart });
      } else {
        tokens.push({ type: "string", text: valPart });
      }
      if (commentPart) tokens.push({ type: "comment", text: commentPart });
      continue;
    }

    tokens.push({ type: "plain", text: line });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  HTML tokenizer                                                     */
/* ------------------------------------------------------------------ */

function tokenizeHtml(code: string): Token[] {
  const tokens: Token[] = [];
  const rx =
    /(<!--[\s\S]*?-->)|(<\/?)([\w-]+)((?:\s+[\w-]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?>)|([^<]+)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = rx.exec(code)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "plain", text: code.slice(lastIndex, match.index) });
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null) {
      // comment
      tokens.push({ type: "comment", text: match[1] });
    } else if (match[2] != null) {
      // opening bracket
      tokens.push({ type: "bracket", text: match[2] });
      // tag name
      tokens.push({ type: "keyword", text: match[3] });
      // attributes
      if (match[4]) {
        const attrRx = /([\w-]+)(\s*=\s*)?("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s>"']+)?/g;
        let attrMatch: RegExpExecArray | null;
        let attrLast = 0;
        const attrs = match[4];
        while ((attrMatch = attrRx.exec(attrs)) !== null) {
          if (attrMatch.index > attrLast) {
            tokens.push({ type: "plain", text: attrs.slice(attrLast, attrMatch.index) });
          }
          attrLast = attrRx.lastIndex;
          tokens.push({ type: "key", text: attrMatch[1] });
          if (attrMatch[2]) tokens.push({ type: "operator", text: attrMatch[2] });
          if (attrMatch[3]) tokens.push({ type: "string", text: attrMatch[3] });
        }
        if (attrLast < attrs.length) {
          tokens.push({ type: "plain", text: attrs.slice(attrLast) });
        }
      }
      // closing bracket
      tokens.push({ type: "bracket", text: match[5] });
    } else if (match[6] != null) {
      tokens.push({ type: "plain", text: match[6] });
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  CSS tokenizer                                                      */
/* ------------------------------------------------------------------ */

function tokenizeCss(code: string): Token[] {
  const tokens: Token[] = [];
  const rx =
    /(\/\*[\s\S]*?\*\/)|(["'](?:[^"'\\]|\\.)*["'])|(@[\w-]+)|(\b-?\d+(?:\.\d+)?(?:%|px|em|rem|vh|vw|s|ms|fr|deg|ch)?)\b|(#[0-9a-fA-F]{3,8})\b|([\w-]+)(\s*:(?!:))|([{}();,>+~*=[\]:])|(\S)/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = rx.exec(code)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "plain", text: code.slice(lastIndex, match.index) });
    }
    lastIndex = rx.lastIndex;

    if (match[1] != null) {
      tokens.push({ type: "comment", text: match[1] });
    } else if (match[2] != null) {
      tokens.push({ type: "string", text: match[2] });
    } else if (match[3] != null) {
      tokens.push({ type: "function", text: match[3] });
    } else if (match[4] != null) {
      tokens.push({ type: "number", text: match[4] });
    } else if (match[5] != null) {
      tokens.push({ type: "number", text: match[5] });
    } else if (match[6] != null) {
      // property: value pattern
      tokens.push({ type: "key", text: match[6] });
      tokens.push({ type: "operator", text: match[7] });
    } else if (match[8] != null) {
      tokens.push({ type: "bracket", text: match[8] });
    } else {
      tokens.push({ type: "plain", text: match[0] });
    }
  }
  if (lastIndex < code.length) {
    tokens.push({ type: "plain", text: code.slice(lastIndex) });
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/*  Tokenize dispatcher                                                */
/* ------------------------------------------------------------------ */

function tokenize(code: string, lang: SyntaxLang): Token[] {
  switch (lang) {
    case "json":
      return tokenizeJson(code);
    case "sql":
      return tokenizeSql(code);
    case "shell":
      return tokenizeShell(code);
    case "diff":
      return tokenizeDiff(code);
    case "python":
      return tokenizePython(code);
    case "typescript":
      return tokenizeTypeScript(code);
    case "yaml":
      return tokenizeYaml(code);
    case "html":
      return tokenizeHtml(code);
    case "css":
      return tokenizeCss(code);
    case "plain":
    default:
      return [{ type: "plain", text: code }];
  }
}

/* ------------------------------------------------------------------ */
/*  Rendering                                                          */
/* ------------------------------------------------------------------ */

const TOKEN_CLASS: Record<Token["type"], string> = {
  plain: "",
  key: "syn-key",
  string: "syn-string",
  number: "syn-number",
  boolean: "syn-boolean",
  null: "syn-null",
  bracket: "syn-bracket",
  keyword: "syn-keyword",
  function: "syn-fn",
  operator: "syn-operator",
  comment: "syn-comment",
  flag: "syn-flag",
  command: "syn-command",
  "diff-add": "syn-diff-add",
  "diff-remove": "syn-diff-remove",
  "diff-hunk": "syn-diff-hunk",
  "diff-header": "syn-diff-header",
};

function renderTokens(tokens: Token[]): ReactNode[] {
  return tokens.map((token, i) => {
    const cls = TOKEN_CLASS[token.type];
    if (!cls) return token.text;
    return (
      <span key={i} className={cls}>
        {token.text}
      </span>
    );
  });
}

/* ------------------------------------------------------------------ */
/*  Public component                                                   */
/* ------------------------------------------------------------------ */

interface SyntaxHighlightProps {
  children: string;
  lang?: SyntaxLang;
  className?: string;
  /** Show line numbers */
  lineNumbers?: boolean;
  /** When present, detect language from file extension before falling back to content detection */
  filePath?: string;
  /** Search query to highlight matches within tokens */
  searchQuery?: string;
  /** Index of the currently focused match (0-based) */
  currentMatchIndex?: number;
  /** Callback reporting total number of matches found */
  onMatchCount?: (count: number) => void;
}

export function SyntaxHighlight({
  children,
  lang,
  className,
  lineNumbers = false,
  filePath,
  searchQuery,
  currentMatchIndex,
  onMatchCount,
}: SyntaxHighlightProps) {
  const resolvedLang = lang ?? (filePath ? detectLangFromPath(filePath) : null) ?? detectLang(children);

  const { rendered, matchCount } = useMemo(() => {
    const tokens = tokenize(children, resolvedLang);

    // --- Search highlighting post-process ---
    function applySearch(nodes: ReactNode[]): { nodes: ReactNode[]; total: number } {
      if (!searchQuery) return { nodes, total: 0 };
      const escaped = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const rx = new RegExp(`(${escaped})`, "gi");
      let globalIdx = 0;
      const result: ReactNode[] = [];

      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        if (typeof node === "string") {
          const parts = node.split(rx);
          for (const part of parts) {
            if (rx.test(part)) {
              rx.lastIndex = 0; // reset after test
              const cls =
                globalIdx === currentMatchIndex
                  ? "syn-search-match syn-search-match--current"
                  : "syn-search-match";
              result.push(<mark key={`s-${i}-${globalIdx}`} className={cls}>{part}</mark>);
              globalIdx++;
            } else {
              if (part) result.push(part);
            }
          }
        } else if (node != null && typeof node === "object" && "props" in (node as React.ReactElement)) {
          const el = node as React.ReactElement<{ children?: ReactNode; className?: string }>;
          const text = typeof el.props.children === "string" ? el.props.children : null;
          if (text) {
            const parts = text.split(rx);
            const inner: ReactNode[] = [];
            for (const part of parts) {
              if (rx.test(part)) {
                rx.lastIndex = 0;
                const cls =
                  globalIdx === currentMatchIndex
                    ? "syn-search-match syn-search-match--current"
                    : "syn-search-match";
                inner.push(<mark key={`s-${i}-${globalIdx}`} className={cls}>{part}</mark>);
                globalIdx++;
              } else {
                if (part) inner.push(part);
              }
            }
            result.push(
              <span key={`w-${i}`} className={el.props.className}>
                {inner}
              </span>,
            );
          } else {
            result.push(node);
          }
        } else {
          result.push(node);
        }
      }
      return { nodes: result, total: globalIdx };
    }

    if (!lineNumbers) {
      const base = renderTokens(tokens);
      const { nodes, total } = applySearch(base);
      return { rendered: nodes, matchCount: total };
    }

    // Split into lines and wrap each with a line number
    const lines = children.split("\n");
    const lineTokens: Token[][] = [];
    let tokenIdx = 0;
    let charIdx = 0;

    for (let i = 0; i < lines.length; i++) {
      const lineEnd = charIdx + lines[i].length;
      const currentLineTokens: Token[] = [];

      while (tokenIdx < tokens.length) {
        const t = tokens[tokenIdx];
        const tEnd = charIdx + t.text.length;

        if (charIdx >= lineEnd) break;

        if (tEnd <= lineEnd) {
          currentLineTokens.push(t);
          charIdx = tEnd;
          tokenIdx++;
        } else {
          // token spans across lines — split
          const sliceLen = lineEnd - charIdx;
          currentLineTokens.push({ type: t.type, text: t.text.slice(0, sliceLen) });
          tokens[tokenIdx] = { type: t.type, text: t.text.slice(sliceLen) };
          charIdx = lineEnd;
          break;
        }
      }

      lineTokens.push(currentLineTokens);

      // skip the newline character
      if (tokenIdx < tokens.length) {
        const t = tokens[tokenIdx];
        if (t.text.startsWith("\n")) {
          if (t.text.length === 1) {
            tokenIdx++;
          } else {
            tokens[tokenIdx] = { type: t.type, text: t.text.slice(1) };
          }
          charIdx++;
        }
      }
    }

    const gutterWidth = String(lines.length).length;
    let totalMatches = 0;

    const lineElements = lineTokens.map((lt, i) => {
      const base = renderTokens(lt);
      const { nodes, total } = applySearch(base);
      totalMatches += total;
      return (
        <div key={i} className="syn-line">
          <span className="syn-line-number" style={{ minWidth: `${gutterWidth + 1}ch` }}>
            {i + 1}
          </span>
          <span className="syn-line-content">{nodes}</span>
        </div>
      );
    });

    return { rendered: lineElements, matchCount: totalMatches };
  }, [children, resolvedLang, lineNumbers, searchQuery, currentMatchIndex]);

  useEffect(() => {
    onMatchCount?.(matchCount);
  }, [matchCount, onMatchCount]);

  return (
    <pre className={cn("syn-root", `syn-lang-${resolvedLang}`, className)}>
      <code>{rendered}</code>
    </pre>
  );
}

/* ------------------------------------------------------------------ */
/*  Utility: highlight JSON for inline use (e.g. DetailsViewer)        */
/* ------------------------------------------------------------------ */

export function renderHighlightedCode(
  code: string,
  options?: { filePath?: string; lang?: SyntaxLang }
): ReactNode[] {
  const resolvedLang = options?.lang
    ?? (options?.filePath ? detectLangFromPath(options.filePath) : null)
    ?? detectLang(code);
  return renderTokens(tokenize(code, resolvedLang));
}

export function highlightJsonInline(code: string): ReactNode[] {
  return renderTokens(tokenizeJson(code));
}
