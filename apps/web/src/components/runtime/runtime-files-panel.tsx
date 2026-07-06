"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { translate } from "@/lib/i18n";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Code2,
  Edit3,
  Eye,
  File,
  FileCode,
  FileJson,
  FilePlus,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  FolderTree,
  GitCompare,
  LoaderCircle,
  MoreHorizontal,
  PanelLeft,
  PanelLeftClose,
  RefreshCcw,
  Save,
  Search,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  RuntimeMutationResult,
  RuntimeWorkspaceDiff,
  RuntimeWorkspaceFile,
  RuntimeWorkspaceSearch,
  RuntimeWorkspaceSearchMatch,
  RuntimeWorkspaceStatus,
  RuntimeWorkspaceTreeEntry,
} from "@/lib/runtime-types";
import { formatBytes } from "@/lib/runtime-ui";
import { cn } from "@/lib/utils";
import {
  SyntaxHighlight,
  getLanguageLabel,
  renderHighlightedCode,
  type SearchOptions,
} from "@/components/shared/syntax-highlight";

type RuntimeMutate = (
  resourcePath: string,
  options?: { searchParams?: URLSearchParams; body?: Record<string, unknown> }
) => Promise<RuntimeMutationResult | Record<string, unknown>>;

type RuntimeFetchResource = <T>(
  resourcePath: string,
  searchParams?: URLSearchParams
) => Promise<T>;

interface RuntimeFilesPanelProps {
  taskId: number;
  workspaceTree: RuntimeWorkspaceTreeEntry[];
  workspaceStatus?: RuntimeWorkspaceStatus;
  mutate: RuntimeMutate;
  fetchResource: RuntimeFetchResource;
}

interface OpenTab {
  path: string;
  content: string;
  dirty: boolean;
  scrollTop: number;
  truncated: boolean;
}

type InlineAction =
  | {
      type: "create";
      kind: "file" | "directory";
      parentPath: string;
      value: string;
    }
  | {
      type: "rename";
      item: RuntimeWorkspaceTreeEntry;
      value: string;
    };

type ViewMode = "file" | "diff";

interface GitChange {
  line: string;
  status: string;
  path: string;
  displayPath: string;
}

interface DiffLineSide {
  lineNumber: number;
  text: string;
}

type DiffRowKind = "context" | "change" | "add" | "remove";

interface DiffRow {
  kind: DiffRowKind;
  oldSide: DiffLineSide | null;
  newSide: DiffLineSide | null;
}

interface DiffMetaRow {
  kind: "hunk" | "meta";
  text: string;
}

interface ParsedDiffFile {
  key: string;
  oldPath: string | null;
  newPath: string | null;
  headerLines: string[];
  rows: Array<DiffRow | DiffMetaRow>;
}

function isDiffMetaRow(row: DiffRow | DiffMetaRow): row is DiffMetaRow {
  return row.kind === "hunk" || row.kind === "meta";
}

function hasBinaryContent(content: string): boolean {
  return content.includes("\0");
}

function isMarkdownFile(path: string): boolean {
  const lower = path.toLowerCase();
  return lower.endsWith(".md") || lower.endsWith(".mdx");
}

function getParentPath(path: string): string {
  const index = path.lastIndexOf("/");
  return index > 0 ? path.slice(0, index) : "";
}

function joinWorkspacePath(parentPath: string, name: string): string {
  const cleanName = name.trim().replace(/^\/+/, "");
  if (!parentPath) return cleanName;
  return `${parentPath.replace(/\/+$/, "")}/${cleanName}`;
}

function getFileName(path: string): string {
  return path.split("/").pop() || path;
}

function isSameOrChildPath(path: string, targetPath: string): boolean {
  return path === targetPath || path.startsWith(`${targetPath}/`);
}

function mapRenamedPath(
  path: string,
  fromPath: string,
  toPath: string,
  isDirectory: boolean,
): string {
  if (path === fromPath) return toPath;
  if (isDirectory && path.startsWith(`${fromPath}/`)) {
    return `${toPath}/${path.slice(fromPath.length + 1)}`;
  }
  return path;
}

function getFileIcon(item: RuntimeWorkspaceTreeEntry, expanded?: boolean) {
  if (item.is_dir) {
    return expanded
      ? <FolderOpen className="h-4 w-4 runtime-file-tree-icon--dir" />
      : <Folder className="h-4 w-4 runtime-file-tree-icon--dir" />;
  }
  const name = item.name.toLowerCase();
  const dotIdx = name.lastIndexOf(".");
  const ext = dotIdx >= 0 ? name.slice(dotIdx) : "";
  if (ext === ".json" || ext === ".jsonl") {
    return <FileJson className="h-4 w-4 runtime-file-tree-icon" />;
  }
  if ([".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go"].includes(ext)) {
    return <FileCode className="h-4 w-4 runtime-file-tree-icon" />;
  }
  if ([".md", ".txt", ".log"].includes(ext)) {
    return <FileText className="h-4 w-4 runtime-file-tree-icon" />;
  }
  return <File className="h-4 w-4 runtime-file-tree-icon" />;
}

function parseGitChanges(statusText: string | undefined): GitChange[] {
  return (statusText || "")
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line && !line.startsWith("##"))
    .map((line) => {
      const status = line.slice(0, 2).trim() || line.slice(0, 2);
      const displayPath = line.slice(3).trim() || line;
      const path = displayPath.includes(" -> ")
        ? displayPath.split(" -> ").at(-1) || displayPath
        : displayPath;
      return { line, status, path, displayPath };
    });
}

function getGitStatusClass(status: string | undefined): string {
  const value = status || "";
  if (value.includes("?")) return "syn-git-status-untracked";
  if (value.includes("U")) return "syn-git-status-conflict";
  if (value.includes("D")) return "syn-git-status-deleted";
  if (value.includes("A")) return "syn-git-status-added";
  if (value.includes("R")) return "syn-git-status-renamed";
  if (value.includes("C")) return "syn-git-status-copied";
  if (value.includes("M")) return "syn-git-status-modified";
  return "";
}

function getChangeForPath(changes: GitChange[], path: string | null | undefined) {
  if (!path) return null;
  return changes.find((change) => change.path === path) ?? null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildSearchRegExp(query: string, options: SearchOptions): RegExp | null {
  if (!query) return null;
  try {
    const source = options.regex ? query : escapeRegExp(query);
    const wordSource = options.wholeWord ? `\\b(?:${source})\\b` : source;
    return new RegExp(wordSource, options.caseSensitive ? "g" : "gi");
  } catch {
    return null;
  }
}

function findSearchRanges(content: string, query: string, options: SearchOptions): Array<[number, number]> {
  const rx = buildSearchRegExp(query, options);
  if (!rx) return [];
  const ranges: Array<[number, number]> = [];
  let match: RegExpExecArray | null;
  while ((match = rx.exec(content)) !== null) {
    if (!match[0]) {
      rx.lastIndex += 1;
      continue;
    }
    ranges.push([match.index, match.index + match[0].length]);
  }
  return ranges;
}

function normalizeDiffPath(value: string): string | null {
  const path = value.trim().replace(/^"|"$/g, "");
  if (!path || path === "/dev/null") return null;
  return path.replace(/^[ab]\//, "");
}

function parseDiffHeaderPath(line: string): string | null {
  return normalizeDiffPath(line.replace(/^(---|\+\+\+)\s+/, "").split("\t")[0] || "");
}

function parseDiffGitPaths(line: string): { oldPath: string | null; newPath: string | null } {
  const match = line.match(/^diff --git\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))/);
  return {
    oldPath: normalizeDiffPath(match?.[1] || match?.[2] || ""),
    newPath: normalizeDiffPath(match?.[3] || match?.[4] || ""),
  };
}

function parseUnifiedDiff(text: string, fallbackPath: string | null | undefined): ParsedDiffFile[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const files: ParsedDiffFile[] = [];
  let current: ParsedDiffFile | null = null;
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;

  const ensureFile = () => {
    if (!current) {
      current = {
        key: fallbackPath || "diff",
        oldPath: fallbackPath || null,
        newPath: fallbackPath || null,
        headerLines: [],
        rows: [],
      };
      files.push(current);
    }
    return current;
  };

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index] ?? "";
    if (!line && index === lines.length - 1) continue;

    if (line.startsWith("diff --git ")) {
      const paths = parseDiffGitPaths(line);
      current = {
        key: `${paths.oldPath || "old"}:${paths.newPath || "new"}:${files.length}`,
        oldPath: paths.oldPath || fallbackPath || null,
        newPath: paths.newPath || fallbackPath || null,
        headerLines: [line],
        rows: [],
      };
      files.push(current);
      inHunk = false;
      continue;
    }

    const file = ensureFile();
    if (!inHunk && line.startsWith("--- ")) {
      file.oldPath = parseDiffHeaderPath(line) || file.oldPath;
      file.headerLines.push(line);
      continue;
    }
    if (!inHunk && line.startsWith("+++ ")) {
      file.newPath = parseDiffHeaderPath(line) || file.newPath;
      file.headerLines.push(line);
      continue;
    }

    const hunk = line.match(/^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@(.*)$/);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      inHunk = true;
      file.rows.push({ kind: "hunk", text: line });
      continue;
    }

    if (!inHunk) {
      if (line.trim()) file.headerLines.push(line);
      continue;
    }

    if (line.startsWith("\\")) {
      file.rows.push({ kind: "meta", text: line });
      continue;
    }

    if (line.startsWith(" ")) {
      const value = line.slice(1);
      file.rows.push({
        kind: "context",
        oldSide: { lineNumber: oldLine, text: value },
        newSide: { lineNumber: newLine, text: value },
      });
      oldLine += 1;
      newLine += 1;
      continue;
    }

    if (line.startsWith("-")) {
      const removals: DiffLineSide[] = [];
      const additions: DiffLineSide[] = [];
      while (index < lines.length && (lines[index] ?? "").startsWith("-")) {
        removals.push({ lineNumber: oldLine, text: (lines[index] ?? "").slice(1) });
        oldLine += 1;
        index += 1;
      }
      while (index < lines.length && (lines[index] ?? "").startsWith("+")) {
        additions.push({ lineNumber: newLine, text: (lines[index] ?? "").slice(1) });
        newLine += 1;
        index += 1;
      }
      index -= 1;
      const rowCount = Math.max(removals.length, additions.length);
      for (let rowIndex = 0; rowIndex < rowCount; rowIndex++) {
        const oldSide = removals[rowIndex] ?? null;
        const newSide = additions[rowIndex] ?? null;
        file.rows.push({
          kind: oldSide && newSide ? "change" : oldSide ? "remove" : "add",
          oldSide,
          newSide,
        });
      }
      continue;
    }

    if (line.startsWith("+")) {
      file.rows.push({
        kind: "add",
        oldSide: null,
        newSide: { lineNumber: newLine, text: line.slice(1) },
      });
      newLine += 1;
      continue;
    }

    file.rows.push({ kind: "meta", text: line });
  }

  return files.filter((file) => file.rows.length > 0 || file.headerLines.length > 0);
}

function RuntimeSideBySideDiff({
  text,
  filePath,
  emptyLabel,
  beforeLabel,
  afterLabel,
}: {
  text: string;
  filePath: string | null;
  emptyLabel: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const files = useMemo(() => parseUnifiedDiff(text, filePath), [filePath, text]);

  if (files.length === 0 || files.every((file) => file.rows.length === 0)) {
    return (
      <div className="runtime-files-diff-empty">
        <GitCompare className="h-5 w-5" />
        <p>{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div className="runtime-files-diff-view">
      {files.map((file) => {
        const effectivePath = file.newPath || file.oldPath || filePath || undefined;
        return (
          <section key={file.key} className="runtime-files-diff-file">
            <header className="runtime-files-diff-file__header">
              <GitCompare className="h-3.5 w-3.5" />
              <span className="truncate">{effectivePath || "diff"}</span>
            </header>
            <div className="runtime-files-diff-grid" role="table" aria-label={effectivePath || "diff"}>
              <div className="runtime-files-diff-grid__head runtime-files-diff-grid__head--old">
                {beforeLabel}
              </div>
              <div className="runtime-files-diff-grid__head runtime-files-diff-grid__head--new">
                {afterLabel}
              </div>
              {file.rows.map((row, index) => {
                if (isDiffMetaRow(row)) {
                  return (
                    <div
                      key={`${row.kind}-${index}-${row.text}`}
                      className={cn("runtime-files-diff-meta", row.kind === "hunk" && "is-hunk")}
                    >
                      {row.text}
                    </div>
                  );
                }
                return (
                  <div
                    key={`${row.kind}-${index}-${row.oldSide?.lineNumber || ""}-${row.newSide?.lineNumber || ""}`}
                    className={cn("runtime-files-diff-row", `runtime-files-diff-row--${row.kind}`)}
                  >
                    <DiffCodeCell side="old" row={row} filePath={effectivePath} />
                    <DiffCodeCell side="new" row={row} filePath={effectivePath} />
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function DiffCodeCell({
  side,
  row,
  filePath,
}: {
  side: "old" | "new";
  row: DiffRow;
  filePath?: string;
}) {
  const data = side === "old" ? row.oldSide : row.newSide;
  return (
    <div
      className={cn(
        "runtime-files-diff-cell",
        `runtime-files-diff-cell--${side}`,
        !data && "is-empty",
      )}
    >
      <span className="runtime-files-diff-gutter">{data?.lineNumber ?? ""}</span>
      <code className="runtime-files-diff-code">
        {data ? renderHighlightedCode(data.text || " ", { filePath }) : " "}
      </code>
    </div>
  );
}

export function RuntimeFilesPanel({
  taskId,
  workspaceTree,
  workspaceStatus,
  mutate,
  fetchResource,
}: RuntimeFilesPanelProps) {
  const { t } = useAppI18n();
  const { showToast } = useToast();
  const [rootItems, setRootItems] = useState<RuntimeWorkspaceTreeEntry[]>(workspaceTree);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, RuntimeWorkspaceTreeEntry[]>>({});
  const [loadingDirs, setLoadingDirs] = useState<Record<string, boolean>>({});
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [editContents, setEditContents] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [inlineAction, setInlineAction] = useState<InlineAction | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchCaseSensitive, setSearchCaseSensitive] = useState(false);
  const [searchWholeWord, setSearchWholeWord] = useState(false);
  const [searchRegex, setSearchRegex] = useState(false);
  const [projectSearchQuery, setProjectSearchQuery] = useState("");
  const [projectSearchCaseSensitive, setProjectSearchCaseSensitive] = useState(false);
  const [projectSearchWholeWord, setProjectSearchWholeWord] = useState(false);
  const [projectSearchRegex, setProjectSearchRegex] = useState(false);
  const [projectSearchOpen, setProjectSearchOpen] = useState(false);
  const [projectSearchLoading, setProjectSearchLoading] = useState(false);
  const [projectSearchResults, setProjectSearchResults] = useState<RuntimeWorkspaceSearchMatch[]>([]);
  const [projectSearchTruncated, setProjectSearchTruncated] = useState(false);
  const [projectSearchError, setProjectSearchError] = useState<string | null>(null);
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  const [matchCount, setMatchCount] = useState(0);
  const [previewMarkdown, setPreviewMarkdown] = useState(false);
  const [cursorLine, setCursorLine] = useState(1);
  const [cursorCol, setCursorCol] = useState(1);
  const [viewMode, setViewMode] = useState<ViewMode>("file");
  const [diffPath, setDiffPath] = useState<string | null>(null);
  const [diffCache, setDiffCache] = useState<Record<string, RuntimeWorkspaceDiff>>({});
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [statusText, setStatusText] = useState(workspaceStatus?.text ?? "");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRootItems(workspaceTree);
  }, [workspaceTree]);

  useEffect(() => {
    setStatusText(workspaceStatus?.text ?? "");
  }, [workspaceStatus?.text]);

  const activeTab = useMemo(
    () => openTabs.find((tab) => tab.path === activeTabPath) ?? null,
    [openTabs, activeTabPath]
  );
  const isEditing = editingPath != null && editingPath === activeTabPath && viewMode === "file";
  const editContent = activeTabPath ? editContents[activeTabPath] ?? "" : "";
  const isBinary = activeTab ? hasBinaryContent(activeTab.content) : false;
  const isTruncated = activeTab?.truncated ?? false;
  const canEdit = Boolean(activeTab && !isBinary && !isTruncated && viewMode === "file");
  const langLabel = activeTab ? getLanguageLabel(activeTab.path) : "";
  const isMarkdown = activeTab ? isMarkdownFile(activeTab.path) : false;
  const activeContent = isEditing ? editContent : (activeTab?.content ?? "");
  const lineCount = activeContent ? activeContent.split("\n").length : 0;
  const changes = useMemo(() => parseGitChanges(statusText), [statusText]);
  const activeChange = getChangeForPath(changes, activeTabPath);
  const searchOptions = useMemo<SearchOptions>(
    () => ({
      caseSensitive: searchCaseSensitive,
      wholeWord: searchWholeWord,
      regex: searchRegex,
    }),
    [searchCaseSensitive, searchWholeWord, searchRegex],
  );
  const projectSearchOptions = useMemo<SearchOptions>(
    () => ({
      caseSensitive: projectSearchCaseSensitive,
      wholeWord: projectSearchWholeWord,
      regex: projectSearchRegex,
    }),
    [projectSearchCaseSensitive, projectSearchWholeWord, projectSearchRegex],
  );
  const isDiffView = viewMode === "diff" && Boolean(diffPath);
  const activeDiff = diffPath ? diffCache[diffPath] : null;

  useEffect(() => {
    if (!activeTab || viewMode !== "file") return;
    if (isTruncated) {
      showToast(t("runtime.files.truncatedFile"), "warning", {
        id: `runtime-files:${taskId}:${activeTab.path}:truncated`,
      });
    }
    if (isBinary) {
      showToast(t("runtime.files.binaryFile"), "warning", {
        id: `runtime-files:${taskId}:${activeTab.path}:binary`,
      });
    }
  }, [activeTab, isBinary, isTruncated, showToast, t, taskId, viewMode]);

  useEffect(() => {
    const query = projectSearchQuery.trim();
    if (query.length < 2) {
      setProjectSearchResults([]);
      setProjectSearchTruncated(false);
      setProjectSearchError(null);
      setProjectSearchLoading(false);
      return;
    }

    let cancelled = false;
    setProjectSearchLoading(true);
    setProjectSearchError(null);
    const timer = window.setTimeout(() => {
      const searchParams = new URLSearchParams();
      searchParams.set("q", query);
      searchParams.set("case_sensitive", String(Boolean(projectSearchOptions.caseSensitive)));
      searchParams.set("whole_word", String(Boolean(projectSearchOptions.wholeWord)));
      searchParams.set("regex", String(Boolean(projectSearchOptions.regex)));
      searchParams.set("max_results", "80");
      void fetchResource<RuntimeWorkspaceSearch>("workspace/search", searchParams)
        .then((payload) => {
          if (cancelled) return;
          setProjectSearchResults(payload.items ?? []);
          setProjectSearchTruncated(Boolean(payload.truncated));
        })
        .catch((error) => {
          if (cancelled) return;
          setProjectSearchResults([]);
          setProjectSearchTruncated(false);
          setProjectSearchError(error instanceof Error ? error.message : t("runtime.files.searchFailed"));
        })
        .finally(() => {
          if (!cancelled) setProjectSearchLoading(false);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [fetchResource, projectSearchOptions, projectSearchQuery, t]);

  const refreshStatus = useCallback(async () => {
    try {
      const payload = await fetchResource<RuntimeWorkspaceStatus>("workspace/status");
      setStatusText(payload.text ?? "");
    } catch {
      // Keep the last known status; the task room will surface broader runtime errors.
    }
  }, [fetchResource]);

  const refreshDirectory = useCallback(
    async (path: string) => {
      const searchParams = new URLSearchParams();
      if (path) searchParams.set("path", path);
      const payload = await fetchResource<{ items?: RuntimeWorkspaceTreeEntry[] }>(
        "workspace/tree",
        searchParams,
      );
      if (path) {
        setExpandedDirs((prev) => ({ ...prev, [path]: payload.items ?? [] }));
      } else {
        setRootItems(payload.items ?? []);
      }
      return payload.items ?? [];
    },
    [fetchResource],
  );

  const refreshAffectedDirectories = useCallback(
    async (...paths: Array<string | null | undefined>) => {
      const parents = Array.from(
        new Set(paths.filter((path): path is string => typeof path === "string").map(getParentPath)),
      );
      if (parents.length === 0) parents.push("");
      await Promise.all(
        parents.map(async (parent) => {
          try {
            await refreshDirectory(parent);
          } catch {
            // Directory refresh is best-effort because the parent query will also refetch.
          }
        }),
      );
    },
    [refreshDirectory],
  );

  const toggleDir = useCallback(
    async (path: string) => {
      if (expandedDirs[path]) {
        setExpandedDirs((prev) => {
          const next = { ...prev };
          delete next[path];
          return next;
        });
        return;
      }

      setLoadingDirs((prev) => ({ ...prev, [path]: true }));
      try {
        await refreshDirectory(path);
      } catch {
        // Silently fail; runtime errors are surfaced in the broader room state.
      } finally {
        setLoadingDirs((prev) => {
          const next = { ...prev };
          delete next[path];
          return next;
        });
      }
    },
    [expandedDirs, refreshDirectory],
  );

  const refreshWorkspace = useCallback(async () => {
    const expandedPaths = Object.keys(expandedDirs);
    await Promise.allSettled([
      refreshDirectory(""),
      ...expandedPaths.map((path) => refreshDirectory(path)),
      refreshStatus(),
    ]);
  }, [expandedDirs, refreshDirectory, refreshStatus]);

  const openFile = useCallback(
    async (path: string) => {
      const existing = openTabs.find((tab) => tab.path === path);
      setViewMode("file");
      setDiffPath(null);
      setDiffError(null);
      if (existing) {
        setFileError(null);
        setActiveTabPath(path);
        return;
      }

      setFileLoading(true);
      setFileError(null);

      try {
        const searchParams = new URLSearchParams();
        searchParams.set("path", path);
        const payload = await fetchResource<RuntimeWorkspaceFile>("workspace/file", searchParams);
        const newTab: OpenTab = {
          path: payload.path,
          content: payload.content,
          dirty: false,
          scrollTop: 0,
          truncated: payload.truncated ?? false,
        };
        setOpenTabs((prev) => [...prev, newTab]);
        setActiveTabPath(payload.path);
        setPreviewMarkdown(false);
      } catch (loadError) {
        const message =
          loadError instanceof Error ? loadError.message : t("runtime.files.loadingFile");
        setFileError(message);
        showToast(message, "error", { id: `runtime-files:${taskId}:file-load` });
      } finally {
        setFileLoading(false);
      }
    },
    [fetchResource, openTabs, showToast, t, taskId],
  );

  const closeTab = useCallback(
    (path: string, e?: React.MouseEvent) => {
      e?.stopPropagation();
      const tab = openTabs.find((item) => item.path === path);
      if (tab?.dirty && !window.confirm(t("runtime.files.discardUnsaved"))) return;

      setOpenTabs((prev) => {
        const filtered = prev.filter((item) => item.path !== path);
        if (activeTabPath === path) {
          const idx = prev.findIndex((item) => item.path === path);
          const next = filtered[Math.min(idx, filtered.length - 1)] ?? null;
          setActiveTabPath(next?.path ?? null);
        }
        return filtered;
      });

      if (editingPath === path) setEditingPath(null);
      setEditContents((prev) => {
        const next = { ...prev };
        delete next[path];
        return next;
      });
    },
    [activeTabPath, editingPath, openTabs, t],
  );

  const handleTreeSelection = useCallback(
    async (item: RuntimeWorkspaceTreeEntry) => {
      if (item.is_dir) {
        await toggleDir(item.path);
        return;
      }
      await openFile(item.path);
    },
    [openFile, toggleDir],
  );

  const startEditing = useCallback(() => {
    if (!activeTab) return;
    setViewMode("file");
    setEditContents((prev) => ({ ...prev, [activeTab.path]: activeTab.content }));
    setEditingPath(activeTab.path);
    setPreviewMarkdown(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [activeTab]);

  const cancelEditing = useCallback(() => {
    if (editingPath) {
      setOpenTabs((prev) =>
        prev.map((tab) => (tab.path === editingPath ? { ...tab, dirty: false } : tab)),
      );
      setEditContents((prev) => {
        const next = { ...prev };
        delete next[editingPath];
        return next;
      });
    }
    setEditingPath(null);
  }, [editingPath]);

  const refreshActiveFile = useCallback(async () => {
    if (!activeTab) return;
    const hasUnsaved = activeTab.dirty;
    if (hasUnsaved && !window.confirm(t("runtime.files.discardUnsaved"))) return;
    setFileLoading(true);
    try {
      const searchParams = new URLSearchParams();
      searchParams.set("path", activeTab.path);
      const payload = await fetchResource<RuntimeWorkspaceFile>("workspace/file", searchParams);
      setOpenTabs((prev) =>
        prev.map((tab) =>
          tab.path === activeTab.path
            ? {
                ...tab,
                content: payload.content,
                dirty: false,
                truncated: payload.truncated ?? false,
              }
            : tab,
        ),
      );
      setEditingPath(null);
      setEditContents((prev) => {
        const next = { ...prev };
        delete next[activeTab.path];
        return next;
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : t("runtime.files.loadingFile");
      setFileError(message);
      showToast(message, "error", { id: `runtime-files:${taskId}:file-refresh` });
    } finally {
      setFileLoading(false);
    }
  }, [activeTab, fetchResource, showToast, t, taskId]);

  const saveFile = useCallback(async () => {
    if (!activeTab || !editingPath) return;
    setSaving(true);

    const content = editContents[editingPath] ?? "";
    try {
      await mutate("workspace/write", { body: { path: editingPath, content } });
      setOpenTabs((prev) =>
        prev.map((tab) =>
          tab.path === editingPath ? { ...tab, content, dirty: false } : tab,
        ),
      );
      setEditingPath(null);
      await Promise.allSettled([refreshAffectedDirectories(editingPath), refreshStatus()]);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("runtime.files.saveFailure");
      showToast(message, "error", { id: `runtime-files:${taskId}:save` });
    } finally {
      setSaving(false);
    }
  }, [
    activeTab,
    editContents,
    editingPath,
    mutate,
    refreshAffectedDirectories,
    refreshStatus,
    showToast,
    t,
    taskId,
  ]);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    setSearchQuery("");
    setMatchCount(0);
    setCurrentMatchIndex(0);
  }, []);

  const loadDiff = useCallback(
    async (path: string) => {
      setDiffLoading(true);
      setDiffError(null);
      try {
        const searchParams = new URLSearchParams();
        searchParams.set("path", path);
        const payload = await fetchResource<RuntimeWorkspaceDiff>("workspace/diff", searchParams);
        setDiffCache((prev) => ({ ...prev, [path]: payload }));
      } catch (error) {
        const message = error instanceof Error ? error.message : t("runtime.files.diffUnavailable");
        setDiffError(message);
        showToast(message, "error", { id: `runtime-files:${taskId}:diff:${path}` });
      } finally {
        setDiffLoading(false);
      }
    },
    [fetchResource, showToast, t, taskId],
  );

  const showDiff = useCallback(
    (path: string, e?: React.MouseEvent) => {
      e?.stopPropagation();
      setViewMode("diff");
      setDiffPath(path);
      setPreviewMarkdown(false);
      closeSearch();
      void loadDiff(path);
    },
    [closeSearch, loadDiff],
  );

  const beginCreate = useCallback(
    async (kind: "file" | "directory", parentPath = "") => {
      if (parentPath && !expandedDirs[parentPath]) {
        await toggleDir(parentPath);
      }
      setInlineAction({ type: "create", kind, parentPath, value: "" });
    },
    [expandedDirs, toggleDir],
  );

  const beginRename = useCallback((item: RuntimeWorkspaceTreeEntry) => {
    setInlineAction({ type: "rename", item, value: item.name });
  }, []);

  const cancelInlineAction = useCallback(() => {
    setInlineAction(null);
  }, []);

  const replaceOpenTabPath = useCallback(
    (fromPath: string, toPath: string, isDirectory = false) => {
      setOpenTabs((prev) =>
        prev.map((tab) => {
          const nextPath = mapRenamedPath(tab.path, fromPath, toPath, isDirectory);
          return nextPath === tab.path ? tab : { ...tab, path: nextPath };
        }),
      );
      setEditContents((prev) => {
        let changed = false;
        const next: Record<string, string> = {};
        for (const [path, content] of Object.entries(prev)) {
          const nextPath = mapRenamedPath(path, fromPath, toPath, isDirectory);
          if (nextPath !== path) changed = true;
          next[nextPath] = content;
        }
        return changed ? next : prev;
      });
      if (activeTabPath) {
        const nextActivePath = mapRenamedPath(activeTabPath, fromPath, toPath, isDirectory);
        if (nextActivePath !== activeTabPath) setActiveTabPath(nextActivePath);
      }
      if (editingPath) {
        const nextEditingPath = mapRenamedPath(editingPath, fromPath, toPath, isDirectory);
        if (nextEditingPath !== editingPath) setEditingPath(nextEditingPath);
      }
    },
    [activeTabPath, editingPath],
  );

  const commitInlineAction = useCallback(async () => {
    if (!inlineAction) return;
    const value = inlineAction.value.trim();
    if (!value) return;

    try {
      if (inlineAction.type === "create") {
        const path = joinWorkspacePath(inlineAction.parentPath, value);
        await mutate("workspace/create", {
          body: { path, kind: inlineAction.kind, content: "" },
        });
        setInlineAction(null);
        await refreshAffectedDirectories(path);
        await refreshStatus();
        if (inlineAction.kind === "file") {
          await openFile(path);
        }
      } else {
        const nextPath = joinWorkspacePath(getParentPath(inlineAction.item.path), value);
        if (nextPath === inlineAction.item.path) {
          setInlineAction(null);
          return;
        }
        await mutate("workspace/rename", {
          body: {
            from_path: inlineAction.item.path,
            to_path: nextPath,
          },
        });
        replaceOpenTabPath(inlineAction.item.path, nextPath, inlineAction.item.is_dir);
        setInlineAction(null);
        await refreshAffectedDirectories(inlineAction.item.path, nextPath);
        await refreshStatus();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t("runtime.files.operationFailed");
      showToast(message, "error", { id: `runtime-files:${taskId}:operation` });
    }
  }, [
    inlineAction,
    mutate,
    openFile,
    refreshAffectedDirectories,
    refreshStatus,
    replaceOpenTabPath,
    showToast,
    t,
    taskId,
  ]);

  const deleteEntry = useCallback(
    async (item: RuntimeWorkspaceTreeEntry, e?: React.MouseEvent) => {
      e?.stopPropagation();
      const confirmMessage = item.is_dir
        ? t("runtime.files.deleteFolderConfirm", { path: item.path })
        : t("runtime.files.deleteFileConfirm", { path: item.path });
      if (!window.confirm(confirmMessage)) return;

      try {
        await mutate("workspace/delete", { body: { path: item.path } });
        setOpenTabs((prev) => {
          const filtered = prev.filter((tab) => !isSameOrChildPath(tab.path, item.path));
          if (activeTabPath && filtered.every((tab) => tab.path !== activeTabPath)) {
            setActiveTabPath(filtered[0]?.path ?? null);
          }
          return filtered;
        });
        setEditContents((prev) => {
          let changed = false;
          const next = { ...prev };
          for (const path of Object.keys(next)) {
            if (isSameOrChildPath(path, item.path)) {
              delete next[path];
              changed = true;
            }
          }
          return changed ? next : prev;
        });
        if (editingPath && isSameOrChildPath(editingPath, item.path)) {
          setEditingPath(null);
        }
        await refreshAffectedDirectories(item.path);
        await refreshStatus();
      } catch (error) {
        const message = error instanceof Error ? error.message : t("runtime.files.operationFailed");
        showToast(message, "error", { id: `runtime-files:${taskId}:delete` });
      }
    },
    [activeTabPath, editingPath, mutate, refreshAffectedDirectories, refreshStatus, showToast, t, taskId],
  );

  const handleEditChange = useCallback(
    (value: string) => {
      if (!activeTabPath) return;
      setEditContents((prev) => ({ ...prev, [activeTabPath]: value }));
      setOpenTabs((prev) =>
        prev.map((tab) => (tab.path === activeTabPath ? { ...tab, dirty: true } : tab)),
      );
    },
    [activeTabPath],
  );

  const handleTextareaKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const textarea = e.currentTarget;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const current = activeTabPath ? editContents[activeTabPath] ?? "" : "";
        const newValue = current.slice(0, start) + "  " + current.slice(end);
        handleEditChange(newValue);
        requestAnimationFrame(() => {
          textarea.selectionStart = textarea.selectionEnd = start + 2;
        });
      }
      if (e.key === "s" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        void saveFile();
      }
    },
    [activeTabPath, editContents, handleEditChange, saveFile],
  );

  const highlightedEditContent = useMemo(() => {
    if (!isEditing || !activeTabPath) return null;
    return renderHighlightedCode(editContent, { filePath: activeTabPath });
  }, [activeTabPath, editContent, isEditing]);

  const syncScroll = useCallback((e: React.UIEvent<HTMLTextAreaElement>) => {
    const { scrollTop, scrollLeft } = e.currentTarget;
    requestAnimationFrame(() => {
      if (gutterRef.current) gutterRef.current.scrollTop = scrollTop;
      if (highlightRef.current) {
        highlightRef.current.scrollTop = scrollTop;
        highlightRef.current.scrollLeft = scrollLeft;
      }
    });
  }, []);

  const editLineNumbers = useMemo(() => {
    const count = editContent.split("\n").length;
    const width = String(count).length;
    return { count, width };
  }, [editContent]);

  const updateCursorPosition = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea || !activeTabPath) return;
    const content = editContents[activeTabPath] ?? "";
    const before = content.slice(0, textarea.selectionStart);
    const line = before.split("\n").length;
    const col = textarea.selectionStart - before.lastIndexOf("\n");
    setCursorLine(line);
    setCursorCol(col);
  }, [activeTabPath, editContents]);

  const openSearch = useCallback(() => {
    if (!activeTab && !isDiffView) return;
    setSearchOpen(true);
    setCurrentMatchIndex(0);
    setTimeout(() => searchInputRef.current?.focus(), 0);
  }, [activeTab, isDiffView]);

  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;

    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        openSearch();
      }
      if (e.key === "Escape" && searchOpen) {
        closeSearch();
      }
    };
    shell.addEventListener("keydown", handler);
    return () => shell.removeEventListener("keydown", handler);
  }, [closeSearch, openSearch, searchOpen]);

  useEffect(() => {
    if (!searchOpen || !isEditing || !searchQuery || matchCount === 0) return;
    const textarea = textareaRef.current;
    if (!textarea) return;

    const content = editContents[activeTabPath!] ?? "";
    const ranges = findSearchRanges(content, searchQuery, searchOptions);
    const range = ranges[currentMatchIndex];

    if (range) {
      textarea.focus();
      textarea.setSelectionRange(range[0], range[1]);
    }
  }, [
    activeTabPath,
    currentMatchIndex,
    editContents,
    isEditing,
    matchCount,
    searchOpen,
    searchOptions,
    searchQuery,
  ]);

  useEffect(() => {
    if (!searchOpen || !isEditing || !searchQuery) {
      if (isEditing) setMatchCount(0);
      return;
    }
    const content = editContents[activeTabPath!] ?? "";
    const count = findSearchRanges(content, searchQuery, searchOptions).length;
    setMatchCount(count);
    setCurrentMatchIndex((current) => (count > 0 && current >= count ? 0 : current));
  }, [activeTabPath, editContents, isEditing, searchOpen, searchOptions, searchQuery]);

  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (matchCount > 0) {
          if (e.shiftKey) {
            setCurrentMatchIndex((prev) => (prev - 1 + matchCount) % matchCount);
          } else {
            setCurrentMatchIndex((prev) => (prev + 1) % matchCount);
          }
        }
      }
      if (e.key === "Escape") {
        closeSearch();
      }
    },
    [closeSearch, matchCount],
  );

  const handleMatchCount = useCallback((count: number) => {
    setMatchCount(count);
  }, []);

  const renderInlineRow = useCallback(
    (depth: number) => {
      if (!inlineAction) return null;
      const icon =
        inlineAction.type === "create" && inlineAction.kind === "directory"
          ? <FolderPlus className="h-4 w-4 runtime-file-tree-icon--dir" />
          : <FilePlus className="h-4 w-4 runtime-file-tree-icon" />;
      return (
        <form
          className="runtime-file-tree-row runtime-file-tree-row--inline"
          onSubmit={(event) => {
            event.preventDefault();
            void commitInlineAction();
          }}
        >
          <div
            className="runtime-file-tree-row__main"
            style={{ paddingLeft: `${0.65 + depth * 1}rem` }}
          >
            <span className="w-[14px] shrink-0" />
            {icon}
            <input
              className="runtime-files-inline-input"
              value={inlineAction.value}
              onChange={(event) =>
                setInlineAction((current) =>
                  current ? { ...current, value: event.target.value } : current,
                )
              }
              onKeyDown={(event) => {
                if (event.key === "Escape") cancelInlineAction();
              }}
              aria-label={t("runtime.files.inlineName")}
              placeholder={
                inlineAction.type === "create"
                  ? inlineAction.kind === "directory"
                    ? t("runtime.files.newFolder")
                    : t("runtime.files.newFile")
                  : t("runtime.files.rename")
              }
              autoFocus
            />
          </div>
          <button
            type="button"
            className="runtime-files-inline-cancel"
            onClick={cancelInlineAction}
            aria-label={t("common.cancel")}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </form>
      );
    },
    [cancelInlineAction, commitInlineAction, inlineAction, t],
  );

  function renderTreeItems(items: RuntimeWorkspaceTreeEntry[], depth: number): React.ReactNode {
    return items.map((item) => {
        const isExpanded = !!expandedDirs[item.path];
        const isLoading = !!loadingDirs[item.path];
        const children = expandedDirs[item.path];
        const isRename = inlineAction?.type === "rename" && inlineAction.item.path === item.path;

        if (isRename) {
          return <div key={item.path}>{renderInlineRow(depth)}</div>;
        }

        return (
          <div key={item.path}>
            <div
              className={cn(
                "runtime-file-tree-row",
                activeTabPath === item.path && viewMode === "file" && "is-active",
              )}
            >
              <button
                type="button"
                onClick={() => void handleTreeSelection(item)}
                className="runtime-file-tree-row__main"
                style={{ paddingLeft: `${0.65 + depth * 1}rem` }}
              >
                {item.is_dir ? (
                  isLoading ? (
                    <LoaderCircle className="h-3.5 w-3.5 shrink-0 animate-spin text-[var(--text-quaternary)]" />
                  ) : isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]" />
                  )
                ) : (
                  <span className="w-[14px] shrink-0" />
                )}
                {getFileIcon(item, isExpanded)}
                <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-[var(--text-primary)]">
                  {item.name}
                </span>
                {!item.is_dir && item.size != null ? (
                  <span className="runtime-files-tree-size">{formatBytes(item.size)}</span>
                ) : null}
              </button>
              <RuntimeFileMenu
                item={item}
                onNewFile={() => void beginCreate("file", item.path)}
                onNewFolder={() => void beginCreate("directory", item.path)}
                onRename={() => beginRename(item)}
                onDelete={(event) => void deleteEntry(item, event)}
                onDiff={(event) => showDiff(item.path, event)}
              />
            </div>
            {isExpanded && inlineAction?.type === "create" && inlineAction.parentPath === item.path
              ? renderInlineRow(depth + 1)
              : null}
            {isExpanded && children && children.length > 0 ? renderTreeItems(children, depth + 1) : null}
          </div>
        );
    });
  }

  const currentPath = isDiffView ? diffPath : activeTab?.path ?? null;
  const editorTitle = currentPath ? getFileName(currentPath) : t("runtime.files.noSelection");
  const diffText = activeDiff?.text || t("runtime.files.noDiff");
  const projectSearchReady = projectSearchQuery.trim().length >= 2;

  function renderProjectSearchPreview(result: RuntimeWorkspaceSearchMatch) {
    const line = result.line || result.preview || "";
    const start = Math.max(0, Math.min(result.start ?? 0, line.length));
    const end = Math.max(start, Math.min(result.end ?? start, line.length));
    return (
      <>
        {line.slice(0, start)}
        {end > start ? <mark>{line.slice(start, end)}</mark> : null}
        {line.slice(end)}
      </>
    );
  }

  return (
    <TooltipProvider delayDuration={250}>
      <div
        className={cn("runtime-files-shell", treeCollapsed && "is-tree-collapsed")}
        ref={shellRef}
        tabIndex={-1}
        data-task-id={taskId}
      >
        <aside className={cn("runtime-files-explorer", treeCollapsed && "is-collapsed")}>
          <div className="runtime-files-explorer__topbar">
            <div className="runtime-files-explorer__title">
              <FolderTree className="h-3.5 w-3.5" />
              <span>{t("runtime.files.explorer")}</span>
            </div>
            <div className="runtime-files-explorer__actions">
              <RuntimeIconButton
                label={t("runtime.files.newFile")}
                icon={FilePlus}
                onClick={() => void beginCreate("file")}
              />
              <RuntimeIconButton
                label={t("runtime.files.newFolder")}
                icon={FolderPlus}
                onClick={() => void beginCreate("directory")}
              />
              <RuntimeIconButton
                label={t("runtime.files.refreshWorkspace")}
                icon={RefreshCcw}
                onClick={() => void refreshWorkspace()}
              />
              <RuntimeIconButton
                label={treeCollapsed ? t("runtime.files.expandSidebar") : t("runtime.files.collapseSidebar")}
                icon={treeCollapsed ? PanelLeft : PanelLeftClose}
                onClick={() => setTreeCollapsed((current) => !current)}
              />
            </div>
          </div>

          <div className="runtime-files-explorer__content">
            {openTabs.length > 0 ? (
              <RuntimeExplorerSection title={t("runtime.files.openEditors")}>
                <div className="runtime-files-open-editors">
                  {openTabs.map((tab) => (
                    <div
                      key={tab.path}
                      className={cn(
                        "runtime-files-open-editor",
                        tab.path === activeTabPath && viewMode === "file" && "is-active",
                      )}
                    >
                      <button
                        type="button"
                        className="runtime-files-open-editor__main"
                        onClick={() => {
                          setActiveTabPath(tab.path);
                          setViewMode("file");
                          setDiffPath(null);
                          setPreviewMarkdown(false);
                        }}
                      >
                        <FileText className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{getFileName(tab.path)}</span>
                        {tab.dirty ? <span className="runtime-files-tab__dot" /> : null}
                      </button>
                      <button
                        type="button"
                        className="runtime-files-open-editor__close"
                        onClick={(event) => closeTab(tab.path, event)}
                        aria-label={t("runtime.files.closeEditor")}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </RuntimeExplorerSection>
            ) : null}

            <RuntimeExplorerSection title={t("runtime.files.workspace")}>
              <div className="runtime-files-tree">
                {inlineAction?.type === "create" && inlineAction.parentPath === ""
                  ? renderInlineRow(0)
                  : null}
                {rootItems.length === 0 ? (
                  <div className="runtime-empty runtime-empty--compact">
                    <FolderTree className="h-5 w-5" />
                    <p>{t("runtime.files.noVisibleFiles")}</p>
                  </div>
                ) : (
                  renderTreeItems(rootItems, 0)
                )}
              </div>
            </RuntimeExplorerSection>

            <RuntimeExplorerSection
              title={t("runtime.files.changes")}
              meta={changes.length ? String(changes.length) : undefined}
            >
              {changes.length > 0 ? (
                <div className="runtime-files-changes runtime-git-syntax">
                  {changes.map((change) => (
                    <div key={`${change.status}-${change.displayPath}`} className="runtime-files-change-row">
                      <button
                        type="button"
                        className={cn("runtime-files-change-main", getGitStatusClass(change.status))}
                        onClick={() => void openFile(change.path)}
                      >
                        <span className="runtime-files-change-status">{change.status}</span>
                        <span className="truncate">{change.displayPath}</span>
                      </button>
                      <button
                        type="button"
                        className="runtime-files-change-diff"
                        onClick={(event) => showDiff(change.path, event)}
                        aria-label={t("runtime.files.showDiffFor", { path: change.displayPath })}
                      >
                        <GitCompare className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="runtime-files-muted-line">{t("runtime.files.noChanges")}</div>
              )}
            </RuntimeExplorerSection>
          </div>
        </aside>

        <main className="runtime-files-workbench">
          <div className="runtime-files-project-search">
            <div className="runtime-files-project-search__field">
              <Search className="h-3.5 w-3.5 shrink-0" />
              <input
                type="text"
                role="searchbox"
                value={projectSearchQuery}
                onChange={(event) => {
                  setProjectSearchQuery(event.target.value);
                  setProjectSearchOpen(true);
                }}
                onFocus={() => setProjectSearchOpen(true)}
                placeholder={t("runtime.files.projectSearchPlaceholder")}
                aria-label={t("runtime.files.projectSearch")}
                className="search-input--custom-clear"
              />
              {projectSearchLoading ? <LoaderCircle className="h-3.5 w-3.5 shrink-0 animate-spin" /> : null}
              {projectSearchQuery ? (
                <button
                  type="button"
                  className="runtime-files-project-search__clear"
                  onClick={() => {
                    setProjectSearchQuery("");
                    setProjectSearchResults([]);
                    setProjectSearchOpen(false);
                  }}
                  aria-label={t("common.cancel")}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
            <div className="runtime-files-project-search__options" aria-label={t("runtime.files.searchOptions")}>
              <button
                type="button"
                className={cn("runtime-files-project-search__toggle", projectSearchCaseSensitive && "is-active")}
                onClick={() => setProjectSearchCaseSensitive((current) => !current)}
                aria-label={t("runtime.files.matchCase")}
                aria-pressed={projectSearchCaseSensitive}
                title={t("runtime.files.matchCase")}
              >
                {translate("generated.runtime.aa_d22b71f7")}</button>
              <button
                type="button"
                className={cn("runtime-files-project-search__toggle", projectSearchWholeWord && "is-active")}
                onClick={() => setProjectSearchWholeWord((current) => !current)}
                aria-label={t("runtime.files.matchWholeWord")}
                aria-pressed={projectSearchWholeWord}
                title={t("runtime.files.matchWholeWord")}
              >
                {translate("generated.runtime.ab_29f3d49e")}</button>
              <button
                type="button"
                className={cn("runtime-files-project-search__toggle", projectSearchRegex && "is-active")}
                onClick={() => setProjectSearchRegex((current) => !current)}
                aria-label={t("runtime.files.useRegex")}
                aria-pressed={projectSearchRegex}
                title={t("runtime.files.useRegex")}
              >
                .*
              </button>
            </div>
            {projectSearchOpen && projectSearchReady ? (
              <div className="runtime-files-project-search__results app-floating-panel">
                <div className="runtime-files-project-search__summary">
                  <span>{t("runtime.files.projectSearchResults")}</span>
                  <span>
                    {projectSearchLoading
                      ? t("runtime.files.searching")
                      : t("runtime.files.searchResultCount", { count: projectSearchResults.length })}
                  </span>
                </div>
                {projectSearchError ? (
                  <div className="runtime-files-project-search__empty">{projectSearchError}</div>
                ) : projectSearchResults.length > 0 ? (
                  <div className="runtime-files-project-search__list">
                    {projectSearchResults.map((result, index) => (
                      <button
                        type="button"
                        key={`${result.path}:${result.line_number}:${result.column}:${index}`}
                        className="runtime-files-project-search__result"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          void openFile(result.path);
                          setProjectSearchOpen(false);
                        }}
                      >
                        <span className="runtime-files-project-search__result-head">
                          <FileText className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate">{result.path}</span>
                          <span className="runtime-files-project-search__line">
                            {result.line_number}:{result.column}
                          </span>
                        </span>
                        <span className="runtime-files-project-search__preview">
                          {renderProjectSearchPreview(result)}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="runtime-files-project-search__empty">{t("runtime.files.noSearchResults")}</div>
                )}
                {projectSearchTruncated ? (
                  <div className="runtime-files-project-search__truncated">{t("runtime.files.searchTruncated")}</div>
                ) : null}
              </div>
            ) : null}
          </div>

          {openTabs.length > 0 ? (
            <div className="runtime-files-tabs">
              {openTabs.map((tab) => (
                <div
                  key={tab.path}
                  className={cn(
                    "runtime-files-tab",
                    tab.path === activeTabPath && viewMode === "file" && "is-active",
                  )}
                >
                  <button
                    type="button"
                    className="runtime-files-tab__main"
                    onClick={() => {
                      setActiveTabPath(tab.path);
                      setViewMode("file");
                      setDiffPath(null);
                      setPreviewMarkdown(false);
                    }}
                  >
                    <span className="truncate">{getFileName(tab.path)}</span>
                    {tab.dirty ? <span className="runtime-files-tab__dot" /> : null}
                  </button>
                  <button
                    type="button"
                    className="runtime-files-tab__close"
                    onClick={(event) => closeTab(tab.path, event)}
                    aria-label={t("runtime.files.closeEditor")}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
              {isDiffView ? (
                <div className="runtime-files-tab is-active">
                  <button type="button" className="runtime-files-tab__main">
                    <GitCompare className="h-3.5 w-3.5" />
                    <span className="truncate">{t("runtime.files.diffTab", { path: getFileName(diffPath || "") })}</span>
                  </button>
                  <button
                    type="button"
                    className="runtime-files-tab__close"
                    onClick={() => {
                      setViewMode("file");
                      setDiffPath(null);
                    }}
                    aria-label={t("runtime.files.closeEditor")}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : null}
            </div>
          ) : isDiffView ? (
            <div className="runtime-files-tabs">
              <div className="runtime-files-tab is-active">
                <button type="button" className="runtime-files-tab__main">
                  <GitCompare className="h-3.5 w-3.5" />
                  <span className="truncate">{t("runtime.files.diffTab", { path: getFileName(diffPath || "") })}</span>
                </button>
              </div>
            </div>
          ) : null}

          <div className="runtime-files-editor">
            <div className="runtime-files-editor__toolbar">
              <div className="runtime-files-editor__file-info">
                <span className="runtime-files-editor__title">{editorTitle}</span>
                {currentPath ? (
                  <span className="runtime-code-inline runtime-files-editor__path">{currentPath}</span>
                ) : null}
                {viewMode === "file" && activeChange ? (
                  <span className={cn("runtime-files-git-pill", getGitStatusClass(activeChange.status))}>
                    {activeChange.status}
                  </span>
                ) : null}
              </div>
              <div className="runtime-files-editor__toolbar-actions">
                <RuntimeIconButton label={t("runtime.files.search")} icon={Search} onClick={openSearch} />
                {isMarkdown && !isEditing && viewMode === "file" ? (
                  <Button
                    type="button"
                    onClick={() => setPreviewMarkdown((current) => !current)}
                    variant="ghost"
                    size="sm"
                    selected={previewMarkdown}
                    className="h-8 rounded-[var(--radius-chip)] px-2.5 text-[0.8125rem]"
                  >
                    {previewMarkdown ? <Code2 className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    {previewMarkdown ? t("common.code") : t("common.preview")}
                  </Button>
                ) : null}
                {activeTab && viewMode === "file" ? (
                  <RuntimeIconButton
                    label={t("runtime.files.showDiff")}
                    icon={GitCompare}
                    onClick={() => showDiff(activeTab.path)}
                  />
                ) : null}
                {activeTab && viewMode === "file" ? (
                  <RuntimeIconButton
                    label={t("runtime.files.refreshFile")}
                    icon={RefreshCcw}
                    onClick={() => void refreshActiveFile()}
                  />
                ) : null}
                {isEditing ? (
                  <>
                    <Button
                      type="button"
                      onClick={() => void saveFile()}
                      disabled={saving}
                      variant="secondary"
                      size="sm"
                      className="h-8 rounded-[var(--radius-chip)] px-2.5 text-[0.8125rem]"
                    >
                      {saving ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4" />
                      )}
                      {t("common.save")}
                    </Button>
                    <Button
                      type="button"
                      onClick={cancelEditing}
                      variant="ghost"
                      size="sm"
                      className="h-8 rounded-[var(--radius-chip)] px-2.5 text-[0.8125rem]"
                    >
                      {t("common.cancel")}
                    </Button>
                  </>
                ) : canEdit ? (
                  <Button
                    type="button"
                    onClick={startEditing}
                    variant="ghost"
                    size="sm"
                    className="h-8 rounded-[var(--radius-chip)] px-2.5 text-[0.8125rem]"
                  >
                    <Edit3 className="h-4 w-4" />
                    {t("common.edit")}
                  </Button>
                ) : null}
                {activeTab && viewMode === "file" ? (
                  <RuntimeIconButton
                    label={t("runtime.files.deleteFile")}
                    icon={Trash2}
                    tone="danger"
                    onClick={() =>
                      void deleteEntry({
                        name: getFileName(activeTab.path),
                        path: activeTab.path,
                        is_dir: false,
                      })
                    }
                  />
                ) : null}
              </div>
            </div>

            {searchOpen ? (
              <div className="runtime-files-search app-floating-panel">
                <Search className="h-3.5 w-3.5 shrink-0" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(event) => {
                    setSearchQuery(event.target.value);
                    setCurrentMatchIndex(0);
                  }}
                  onKeyDown={handleSearchKeyDown}
                  placeholder={t("runtime.files.searchPlaceholder")}
                  autoFocus
                />
                {searchQuery ? (
                  <span className="runtime-files-search__count">
                    {matchCount > 0 ? `${currentMatchIndex + 1}/${matchCount}` : "0/0"}
                  </span>
                ) : null}
                <div className="runtime-files-search__options" aria-label={t("runtime.files.searchOptions")}>
                  <button
                    type="button"
                    className={cn("runtime-files-search__toggle", searchCaseSensitive && "is-active")}
                    onClick={() => {
                      setSearchCaseSensitive((current) => !current);
                      setCurrentMatchIndex(0);
                    }}
                    aria-label={t("runtime.files.matchCase")}
                    aria-pressed={searchCaseSensitive}
                    title={t("runtime.files.matchCase")}
                  >
                    {translate("generated.runtime.aa_d22b71f7")}</button>
                  <button
                    type="button"
                    className={cn("runtime-files-search__toggle", searchWholeWord && "is-active")}
                    onClick={() => {
                      setSearchWholeWord((current) => !current);
                      setCurrentMatchIndex(0);
                    }}
                    aria-label={t("runtime.files.matchWholeWord")}
                    aria-pressed={searchWholeWord}
                    title={t("runtime.files.matchWholeWord")}
                  >
                    {translate("generated.runtime.ab_29f3d49e")}</button>
                  <button
                    type="button"
                    className={cn("runtime-files-search__toggle", searchRegex && "is-active")}
                    onClick={() => {
                      setSearchRegex((current) => !current);
                      setCurrentMatchIndex(0);
                    }}
                    aria-label={t("runtime.files.useRegex")}
                    aria-pressed={searchRegex}
                    title={t("runtime.files.useRegex")}
                  >
                    .*
                  </button>
                </div>
                <button type="button" onClick={closeSearch} aria-label={t("common.cancel")}>
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : null}

            {fileLoading || diffLoading ? (
              <div className="runtime-empty">
                <LoaderCircle className="h-5 w-5 animate-spin" />
                <p>{fileLoading ? t("runtime.files.loadingFile") : t("runtime.files.loadingDiff")}</p>
              </div>
            ) : fileError && !activeTab ? (
              <div className="runtime-empty">
                <AlertTriangle className="h-5 w-5" />
                <p>{t("runtime.files.openFileToView")}</p>
              </div>
            ) : isDiffView ? (
              <div className="runtime-files-editor__content">
                {diffError ? (
                  <div className="runtime-empty">
                    <GitCompare className="h-5 w-5" />
                    <p>{t("runtime.files.noDiff")}</p>
                  </div>
                ) : (
                  <RuntimeSideBySideDiff
                    text={diffText}
                    filePath={diffPath}
                    emptyLabel={t("runtime.files.noDiff")}
                    beforeLabel={t("runtime.files.before")}
                    afterLabel={t("runtime.files.after")}
                  />
                )}
              </div>
            ) : activeTab ? (
              <>
                {isBinary ? (
                  <div className="runtime-empty">
                    <AlertTriangle className="h-5 w-5" />
                    <p>{t("runtime.files.binaryFile")}</p>
                  </div>
                ) : isEditing ? (
                  <div className="runtime-files-editor__edit-area">
                    <div className="runtime-files-editor__gutter" ref={gutterRef}>
                      {Array.from({ length: editLineNumbers.count }, (_, index) => (
                        <div key={index} className="runtime-files-gutter__line">
                          {index + 1}
                        </div>
                      ))}
                    </div>
                    <div className="runtime-files-editor__code-wrap">
                      <pre
                        className="runtime-files-editor__highlight"
                        ref={highlightRef}
                        aria-hidden="true"
                      >
                        <code>
                          {highlightedEditContent}
                          {editContent.endsWith("\n") ? "\n" : null}
                        </code>
                      </pre>
                      <textarea
                        ref={textareaRef}
                        className="runtime-files-textarea--highlighted"
                        value={editContent}
                        onChange={(event) => handleEditChange(event.target.value)}
                        onKeyDown={handleTextareaKeyDown}
                        onScroll={syncScroll}
                        onSelect={updateCursorPosition}
                        onClick={updateCursorPosition}
                        onKeyUp={updateCursorPosition}
                        onFocus={() => {
                          requestAnimationFrame(() => {
                            if (textareaRef.current && highlightRef.current) {
                              highlightRef.current.scrollTop = textareaRef.current.scrollTop;
                              highlightRef.current.scrollLeft = textareaRef.current.scrollLeft;
                            }
                          });
                        }}
                        spellCheck={false}
                      />
                    </div>
                  </div>
                ) : isMarkdown && previewMarkdown ? (
                  <div className="runtime-files-editor__content runtime-files-markdown-preview">
                    <div className="session-richtext">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                        {activeTab.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  <div className="runtime-files-editor__content">
                    <SyntaxHighlight
                      lineNumbers
                      filePath={activeTab.path}
                      className="runtime-code-block runtime-code-block--tall"
                      searchQuery={searchOpen ? searchQuery : undefined}
                      searchOptions={searchOptions}
                      currentMatchIndex={currentMatchIndex}
                      onMatchCount={handleMatchCount}
                    >
                      {activeTab.content}
                    </SyntaxHighlight>
                  </div>
                )}
              </>
            ) : (
              <div className="runtime-empty">
                <FolderTree className="h-5 w-5" />
                <p>{t("runtime.files.openFileToView")}</p>
              </div>
            )}

            <div className="runtime-files-statusbar">
              {isDiffView ? (
                <>
                  <span>{t("runtime.files.diff")}</span>
                  <span>{diffPath || "—"}</span>
                  {activeDiff?.truncated ? <span>{t("runtime.files.truncated")}</span> : null}
                </>
              ) : (
                <>
                  <span>
                    {lineCount} {t("common.lines")}
                  </span>
                  <span>{formatBytes(new TextEncoder().encode(activeContent).byteLength)}</span>
                  <span>{langLabel || t("runtime.files.noSelection")}</span>
                  <span>{translate("generated.runtime.utf_8_11586a5c")}</span>
                  <span>{activeTab?.dirty ? t("runtime.files.unsaved") : t("runtime.files.saved")}</span>
                  {activeChange ? <span>{activeChange.status}</span> : null}
                  {isEditing ? <span>{translate("generated.runtime.ln_7be0e8d8")}{cursorLine}{translate("generated.runtime.col_f6154bf3")}{cursorCol}</span> : null}
                </>
              )}
            </div>
          </div>
        </main>
      </div>
    </TooltipProvider>
  );
}

function RuntimeExplorerSection({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="runtime-files-explorer-section">
      <header className="runtime-files-explorer-section__header">
        <span>{title}</span>
        {meta ? <span>{meta}</span> : null}
      </header>
      {children}
    </section>
  );
}

function RuntimeIconButton({
  label,
  icon: Icon,
  onClick,
  tone = "neutral",
}: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  tone?: "neutral" | "danger";
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          className={cn(
            "runtime-files-icon-button",
            tone === "danger" && "runtime-files-icon-button--danger",
          )}
          aria-label={label}
        >
          <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function RuntimeFileMenu({
  item,
  onNewFile,
  onNewFolder,
  onRename,
  onDelete,
  onDiff,
}: {
  item: RuntimeWorkspaceTreeEntry;
  onNewFile: () => void;
  onNewFolder: () => void;
  onRename: () => void;
  onDelete: (event: React.MouseEvent<HTMLButtonElement>) => void;
  onDiff: (event: React.MouseEvent<HTMLButtonElement>) => void;
}) {
  const { t } = useAppI18n();
  const [open, setOpen] = useState(false);
  const runAction =
    (action: () => void) => (event: React.MouseEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      action();
      setOpen(false);
    };
  const runEventAction =
    (action: (event: React.MouseEvent<HTMLButtonElement>) => void) =>
    (event: React.MouseEvent<HTMLButtonElement>) => {
      action(event);
      setOpen(false);
    };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="runtime-file-tree-row__menu"
          aria-label={item.is_dir ? t("runtime.files.folderActions") : t("runtime.files.fileActions")}
          aria-haspopup="menu"
          onClick={(event) => event.stopPropagation()}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={4}
        className="w-[12rem] p-1.5"
        role="menu"
        aria-label={item.is_dir ? t("runtime.files.folderActions") : t("runtime.files.fileActions")}
      >
        <div className="flex flex-col gap-1">
          {item.is_dir ? (
            <>
              <RuntimeFileMenuItem
                icon={FilePlus}
                label={t("runtime.files.newFile")}
                onClick={runAction(onNewFile)}
              />
              <RuntimeFileMenuItem
                icon={FolderPlus}
                label={t("runtime.files.newFolder")}
                onClick={runAction(onNewFolder)}
              />
              <RuntimeFileMenuDivider />
            </>
          ) : (
            <RuntimeFileMenuItem
              icon={GitCompare}
              label={t("runtime.files.showDiff")}
              onClick={runEventAction(onDiff)}
            />
          )}
          <RuntimeFileMenuItem
            icon={Edit3}
            label={t("runtime.files.rename")}
            onClick={runAction(onRename)}
          />
          <RuntimeFileMenuDivider />
          <RuntimeFileMenuItem
            icon={Trash2}
            label={item.is_dir ? t("runtime.files.deleteFolder") : t("runtime.files.deleteFile")}
            tone="danger"
            onClick={runEventAction(onDelete)}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function RuntimeFileMenuDivider() {
  return <div className="my-1 h-px bg-[var(--divider-hair)]" aria-hidden="true" />;
}

function RuntimeFileMenuItem({
  icon: Icon,
  label,
  onClick,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
  tone?: "neutral" | "danger";
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cn(
        "flex h-8 w-full items-center gap-2 rounded-[var(--radius-chip)] px-2 text-left text-[13px] font-medium outline-none",
        "transition-[background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-visible:bg-[var(--hover-tint)] focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]",
        tone === "danger"
          ? "text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
      <span className="truncate">{label}</span>
    </button>
  );
}
