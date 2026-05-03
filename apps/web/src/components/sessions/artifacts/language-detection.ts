// Maps a file extension (without the leading dot) to a canonical language id.
// Used by the code viewer to label the snippet and pick the right syntax
// theme when shiki is wired up. Keep the list small and high-signal — adding
// every long-tail extension is not a goal.

const EXTENSION_TO_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  swift: "swift",
  c: "c",
  h: "c",
  cpp: "cpp",
  hpp: "cpp",
  cc: "cpp",
  cs: "csharp",
  php: "php",
  pl: "perl",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  fish: "bash",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  ini: "ini",
  env: "ini",
  xml: "xml",
  html: "html",
  htm: "html",
  css: "css",
  scss: "scss",
  sass: "sass",
  less: "less",
  sql: "sql",
  graphql: "graphql",
  gql: "graphql",
  proto: "protobuf",
  dockerfile: "dockerfile",
  md: "markdown",
  mdx: "markdown",
  hcl: "hcl",
  tf: "hcl",
};

export function detectLanguage(filename: string | null | undefined): string {
  if (!filename) return "plaintext";
  const lower = filename.toLowerCase();
  if (lower === "dockerfile" || lower.endsWith("/dockerfile")) return "dockerfile";
  const dotIndex = lower.lastIndexOf(".");
  if (dotIndex === -1) return "plaintext";
  const ext = lower.slice(dotIndex + 1);
  return EXTENSION_TO_LANG[ext] ?? "plaintext";
}
