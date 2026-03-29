"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  FolderTree,
  LoaderCircle,
  PanelLeft,
  PanelLeftClose,
  RefreshCcw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type {
  RuntimeMutationResult,
  RuntimeWorkspaceFile,
  RuntimeWorkspaceTreeEntry,
} from "@/lib/runtime-types";
import { formatBytes } from "@/lib/runtime-ui";
import { cn } from "@/lib/utils";
import {
  SyntaxHighlight,
  getLanguageLabel,
  renderHighlightedCode,
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

function hasBinaryContent(content: string): boolean {
  return content.includes("\0");
}

function isMarkdownFile(path: string): boolean {
  const lower = path.toLowerCase();
  return lower.endsWith(".md") || lower.endsWith(".mdx");
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
  if (ext === ".json" || ext === ".jsonl") return <FileJson className="h-4 w-4 runtime-file-tree-icon" />;
  if ([".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go"].includes(ext)) return <FileCode className="h-4 w-4 runtime-file-tree-icon" />;
  if ([".md", ".txt", ".log"].includes(ext)) return <FileText className="h-4 w-4 runtime-file-tree-icon" />;
  return <File className="h-4 w-4 runtime-file-tree-icon" />;
}

export function RuntimeFilesPanel({
  taskId,
  workspaceTree,
  mutate,
  fetchResource,
}: RuntimeFilesPanelProps) {
  const { t } = useAppI18n();
  // Expandable tree state
  const [expandedDirs, setExpandedDirs] = useState<Record<string, RuntimeWorkspaceTreeEntry[]>>({});
  const [loadingDirs, setLoadingDirs] = useState<Record<string, boolean>>({});
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  // Sidebar collapse
  const [treeCollapsed, setTreeCollapsed] = useState(false);

  // Multi-file tabs
  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [editContents, setEditContents] = useState<Record<string, string>>({});

  // Editor
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Create
  const [creating, setCreating] = useState(false);
  const [newFileName, setNewFileName] = useState("");

  // Search
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  const [matchCount, setMatchCount] = useState(0);

  // Markdown preview
  const [previewMarkdown, setPreviewMarkdown] = useState(false);

  // Cursor tracking
  const [cursorLine, setCursorLine] = useState(1);
  const [cursorCol, setCursorCol] = useState(1);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);

  // Derived state
  const activeTab = useMemo(
    () => openTabs.find((t) => t.path === activeTabPath) ?? null,
    [openTabs, activeTabPath]
  );
  const isEditing = editingPath != null && editingPath === activeTabPath;
  const editContent = activeTabPath ? editContents[activeTabPath] ?? "" : "";
  const isBinary = activeTab ? hasBinaryContent(activeTab.content) : false;
  const isTruncated = activeTab?.truncated ?? false;
  const canEdit = activeTab && !isBinary && !isTruncated;
  const langLabel = activeTab ? getLanguageLabel(activeTab.path) : "";
  const isMarkdown = activeTab ? isMarkdownFile(activeTab.path) : false;

  // Line count & content for status bar
  const activeContent = isEditing ? editContent : (activeTab?.content ?? "");
  const lineCount = activeContent ? activeContent.split("\n").length : 0;

  // Toggle directory expand/collapse
  const toggleDir = useCallback(
    async (path: string) => {
      // If already expanded, collapse
      if (expandedDirs[path]) {
        setExpandedDirs((prev) => {
          const next = { ...prev };
          delete next[path];
          return next;
        });
        return;
      }

      // Load children
      setLoadingDirs((prev) => ({ ...prev, [path]: true }));
      try {
        const searchParams = new URLSearchParams();
        searchParams.set("path", path);
        const payload = await fetchResource<{ items?: RuntimeWorkspaceTreeEntry[] }>(
          "workspace/tree",
          searchParams
        );
        setExpandedDirs((prev) => ({ ...prev, [path]: payload.items ?? [] }));
      } catch {
        // Silently fail — dir just won't expand
      } finally {
        setLoadingDirs((prev) => {
          const next = { ...prev };
          delete next[path];
          return next;
        });
      }
    },
    [expandedDirs, fetchResource]
  );

  // Refresh all: clear cache, re-fetch expanded dirs
  const refreshTree = useCallback(async () => {
    const expandedPaths = Object.keys(expandedDirs);
    // Clear cache
    setExpandedDirs({});
    // Re-fetch all previously expanded dirs
    for (const dirPath of expandedPaths) {
      try {
        const searchParams = new URLSearchParams();
        searchParams.set("path", dirPath);
        const payload = await fetchResource<{ items?: RuntimeWorkspaceTreeEntry[] }>(
          "workspace/tree",
          searchParams
        );
        setExpandedDirs((prev) => ({ ...prev, [dirPath]: payload.items ?? [] }));
      } catch {
        // Skip dirs that fail
      }
    }
  }, [expandedDirs, fetchResource]);

  const openFile = useCallback(
    async (path: string) => {
      // If tab already open, just activate
      const existing = openTabs.find((t) => t.path === path);
      if (existing) {
        setActiveTabPath(path);
        return;
      }

      setFileLoading(true);
      setFileError(null);
      setSaveError(null);

      try {
        const searchParams = new URLSearchParams();
        searchParams.set("path", path);
        const payload = await fetchResource<RuntimeWorkspaceFile>(
          "workspace/file",
          searchParams
        );
        const newTab: OpenTab = {
          path: payload.path,
          content: payload.content,
          dirty: false,
          scrollTop: 0,
          truncated: payload.truncated ?? false,
        };
        setOpenTabs((prev) => [...prev, newTab]);
        setActiveTabPath(payload.path);
        // Reset preview state when opening a new file
        setPreviewMarkdown(false);
      } catch (loadError) {
        setFileError(loadError instanceof Error ? loadError.message : t("runtime.files.loadingFile"));
      } finally {
        setFileLoading(false);
      }
    },
    [fetchResource, openTabs, t]
  );

  const closeTab = useCallback(
    (path: string, e?: React.MouseEvent) => {
      e?.stopPropagation();
      const tab = openTabs.find((t) => t.path === path);
      if (tab?.dirty && !window.confirm(t("runtime.files.discardUnsaved"))) return;

      setOpenTabs((prev) => {
        const filtered = prev.filter((t) => t.path !== path);
        if (activeTabPath === path) {
          const idx = prev.findIndex((t) => t.path === path);
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
      setSaveError(null);
    },
    [openTabs, activeTabPath, editingPath, t]
  );

  const handleTreeSelection = useCallback(
    async (item: RuntimeWorkspaceTreeEntry) => {
      if (item.is_dir) {
        await toggleDir(item.path);
        return;
      }
      await openFile(item.path);
    },
    [toggleDir, openFile]
  );

  const startEditing = useCallback(() => {
    if (!activeTab) return;
    setEditContents((prev) => ({ ...prev, [activeTab.path]: activeTab.content }));
    setEditingPath(activeTab.path);
    setSaveError(null);
    setPreviewMarkdown(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [activeTab]);

  const cancelEditing = useCallback(() => {
    setEditingPath(null);
    setSaveError(null);
  }, []);

  const saveFile = useCallback(async () => {
    if (!activeTab || !editingPath) return;
    setSaving(true);
    setSaveError(null);

    const content = editContents[editingPath] ?? "";
    try {
      await mutate("workspace/write", {
        body: { path: editingPath, content },
      });
      setOpenTabs((prev) =>
        prev.map((t) =>
          t.path === editingPath ? { ...t, content, dirty: false } : t
        )
      );
      setEditingPath(null);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : t("runtime.files.saveFailure"));
    } finally {
      setSaving(false);
    }
  }, [activeTab, editingPath, editContents, mutate, t]);

  const deleteFile = useCallback(
    async (path: string, e: React.MouseEvent) => {
      e.stopPropagation();
      if (!window.confirm(t("runtime.files.deleteFileConfirm", { path }))) return;

      try {
        await mutate("workspace/delete", { body: { path } });
        // Close tab if open
        if (openTabs.some((t) => t.path === path)) {
          setOpenTabs((prev) => {
            const filtered = prev.filter((t) => t.path !== path);
            if (activeTabPath === path) {
              setActiveTabPath(filtered[0]?.path ?? null);
            }
            return filtered;
          });
          if (editingPath === path) setEditingPath(null);
        }
        // Refresh the parent directory's children
        const parentPath = path.includes("/") ? path.split("/").slice(0, -1).join("/") : "";
        if (parentPath && expandedDirs[parentPath]) {
          // Re-fetch parent dir
          const searchParams = new URLSearchParams();
          searchParams.set("path", parentPath);
          const payload = await fetchResource<{ items?: RuntimeWorkspaceTreeEntry[] }>(
            "workspace/tree",
            searchParams
          );
          setExpandedDirs((prev) => ({ ...prev, [parentPath]: payload.items ?? [] }));
        }
        // Note: root-level deletions are handled by workspaceTree prop update from parent
      } catch {
        // error handled by feedback in task room
      }
    },
    [mutate, openTabs, activeTabPath, editingPath, expandedDirs, fetchResource, t]
  );

  const createFile = useCallback(async () => {
    const name = newFileName.trim();
    if (!name) return;

    try {
      await mutate("workspace/create", {
        body: { path: name, content: "" },
      });
      setCreating(false);
      setNewFileName("");
      // Refresh parent dir if it's expanded
      const parentPath = name.includes("/") ? name.split("/").slice(0, -1).join("/") : "";
      if (parentPath && expandedDirs[parentPath]) {
        const searchParams = new URLSearchParams();
        searchParams.set("path", parentPath);
        const payload = await fetchResource<{ items?: RuntimeWorkspaceTreeEntry[] }>(
          "workspace/tree",
          searchParams
        );
        setExpandedDirs((prev) => ({ ...prev, [parentPath]: payload.items ?? [] }));
      }
      await openFile(name);
    } catch {
      // error handled by feedback
    }
  }, [newFileName, mutate, expandedDirs, fetchResource, openFile]);

  // Edit content change handler — marks tab dirty
  const handleEditChange = useCallback(
    (value: string) => {
      if (!activeTabPath) return;
      setEditContents((prev) => ({ ...prev, [activeTabPath]: value }));
      setOpenTabs((prev) =>
        prev.map((t) =>
          t.path === activeTabPath ? { ...t, dirty: true } : t
        )
      );
    },
    [activeTabPath]
  );

  const handleTextareaKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const ta = e.currentTarget;
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        const current = activeTabPath ? editContents[activeTabPath] ?? "" : "";
        const newValue = current.slice(0, start) + "  " + current.slice(end);
        handleEditChange(newValue);
        requestAnimationFrame(() => {
          ta.selectionStart = ta.selectionEnd = start + 2;
        });
      }
      if (e.key === "s" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        void saveFile();
      }
    },
    [activeTabPath, editContents, handleEditChange, saveFile]
  );

  // Memoized syntax highlighting for edit mode
  const highlightedEditContent = useMemo(() => {
    if (!isEditing || !activeTabPath) return null;
    return renderHighlightedCode(editContent, { filePath: activeTabPath });
  }, [isEditing, activeTabPath, editContent]);

  // Scroll sync: gutter + highlight layer
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

  // Line numbers for edit mode
  const editLineNumbers = useMemo(() => {
    const count = editContent.split("\n").length;
    const width = String(count).length;
    return { count, width };
  }, [editContent]);

  // Cursor position tracking
  const updateCursorPosition = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta || !activeTabPath) return;
    const content = editContents[activeTabPath] ?? "";
    const before = content.slice(0, ta.selectionStart);
    const line = before.split("\n").length;
    const col = ta.selectionStart - before.lastIndexOf("\n");
    setCursorLine(line);
    setCursorCol(col);
  }, [activeTabPath, editContents]);

  const closeSearch = useCallback(() => {
    setSearchOpen(false);
    setSearchQuery("");
    setMatchCount(0);
    setCurrentMatchIndex(0);
  }, []);

  // Keyboard handler for search
  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;

    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        if (activeTab) {
          setSearchOpen(true);
          setCurrentMatchIndex(0);
          setTimeout(() => searchInputRef.current?.focus(), 0);
        }
      }
      if (e.key === "Escape" && searchOpen) {
        closeSearch();
      }
    };
    shell.addEventListener("keydown", handler);
    return () => shell.removeEventListener("keydown", handler);
  }, [activeTab, searchOpen, closeSearch]);

  // Search navigation in editor mode
  useEffect(() => {
    if (!searchOpen || !isEditing || !searchQuery || matchCount === 0) return;
    const ta = textareaRef.current;
    if (!ta) return;

    const content = editContents[activeTabPath!] ?? "";
    const query = searchQuery.toLowerCase();
    const lowerContent = content.toLowerCase();
    let idx = -1;
    let count = 0;
    let matchStart = 0;
    let matchEnd = 0;

    let searchFrom = 0;
    while (true) {
      idx = lowerContent.indexOf(query, searchFrom);
      if (idx === -1) break;
      if (count === currentMatchIndex) {
        matchStart = idx;
        matchEnd = idx + searchQuery.length;
      }
      count++;
      searchFrom = idx + 1;
    }

    if (count > 0) {
      ta.focus();
      ta.setSelectionRange(matchStart, matchEnd);
    }
  }, [searchOpen, isEditing, searchQuery, currentMatchIndex, matchCount, activeTabPath, editContents]);

  // Search match count for editor mode
  useEffect(() => {
    if (!searchOpen || !isEditing || !searchQuery) {
      if (isEditing) setMatchCount(0);
      return;
    }
    const content = editContents[activeTabPath!] ?? "";
    const query = searchQuery.toLowerCase();
    const lowerContent = content.toLowerCase();
    let count = 0;
    let searchFrom = 0;
    while (true) {
      const idx = lowerContent.indexOf(query, searchFrom);
      if (idx === -1) break;
      count++;
      searchFrom = idx + 1;
    }
    setMatchCount(count);
  }, [searchOpen, isEditing, searchQuery, activeTabPath, editContents]);

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
    [matchCount, closeSearch]
  );

  const handleMatchCount = useCallback((count: number) => {
    setMatchCount(count);
  }, []);

  // Recursive tree rendering
  const renderTreeItems = useCallback(
    (items: RuntimeWorkspaceTreeEntry[], depth: number): React.ReactNode => {
      return items.map((item) => {
        const isExpanded = !!expandedDirs[item.path];
        const isLoading = !!loadingDirs[item.path];
        const children = expandedDirs[item.path];

        return (
          <div key={item.path}>
            <div
              className={cn(
                "runtime-file-tree-row",
                activeTabPath === item.path && "is-active"
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
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin shrink-0 text-[var(--text-quaternary)]" />
                  ) : isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]" />
                  )
                ) : (
                  <span style={{ width: "14px", flexShrink: 0 }} />
                )}
                {getFileIcon(item, isExpanded)}
                <div className="min-w-0" style={{ flex: 1 }}>
                  <p className="truncate text-sm text-[var(--text-primary)]">
                    {item.name}
                  </p>
                  <p className="truncate text-xs text-[var(--text-quaternary)]">
                    {item.is_dir
                      ? t("runtime.files.folder")
                      : item.size != null
                        ? formatBytes(item.size)
                        : t("runtime.files.file")}
                  </p>
                </div>
              </button>
              {!item.is_dir ? (
                <div className="runtime-file-tree-row__actions">
                  <button
                    type="button"
                    onClick={(e) => void deleteFile(item.path, e)}
                    className="runtime-ghost-button runtime-ghost-button--icon runtime-ghost-button--danger-hover"
                    title={t("runtime.files.deleteFile")}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : null}
            </div>
            {/* Render children if expanded */}
            {isExpanded && children && children.length > 0 && (
              renderTreeItems(children, depth + 1)
            )}
          </div>
        );
      });
    },
    [expandedDirs, loadingDirs, activeTabPath, handleTreeSelection, deleteFile, t]
  );

  return (
    <div className="runtime-files-shell" ref={shellRef} tabIndex={-1} data-task-id={taskId}>
      <div className="runtime-files-header">
        <div className="runtime-files-header__nav">
          <button
            type="button"
            onClick={() => setTreeCollapsed((c) => !c)}
            className="runtime-ghost-button runtime-ghost-button--icon"
            title={treeCollapsed ? t("runtime.files.expandSidebar") : t("runtime.files.collapseSidebar")}
          >
            {treeCollapsed ? (
              <PanelLeft className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
          <span className="runtime-code-inline">/</span>
        </div>
        <div className="runtime-files-header__actions">
          <button
            type="button"
            onClick={() => setCreating((c) => !c)}
            className="runtime-ghost-button"
          >
            <FilePlus className="h-4 w-4" />
            {t("runtime.files.new")}
          </button>
          <button
            type="button"
            onClick={() => void refreshTree()}
            className="runtime-ghost-button"
          >
            <RefreshCcw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {creating ? (
        <div className="runtime-files-create-form">
          <input
            type="text"
            value={newFileName}
            onChange={(e) => setNewFileName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void createFile();
              if (e.key === "Escape") {
                setCreating(false);
                setNewFileName("");
              }
            }}
            placeholder={t("runtime.files.createPathPlaceholder")}
            className="runtime-files-create-input"
            autoFocus
          />
          <button
            type="button"
            onClick={() => void createFile()}
            className="runtime-ghost-button"
            disabled={!newFileName.trim()}
          >
            {t("runtime.files.createFile")}
          </button>
          <button
            type="button"
            onClick={() => {
              setCreating(false);
              setNewFileName("");
            }}
            className="runtime-ghost-button runtime-ghost-button--icon"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      {/* Tab bar */}
      {openTabs.length > 0 && (
        <div className="runtime-files-tabs">
          {openTabs.map((tab) => (
            <button
              key={tab.path}
              type="button"
              className={cn("runtime-files-tab", tab.path === activeTabPath && "is-active")}
              onClick={() => {
                setActiveTabPath(tab.path);
                // Reset preview when switching tabs
                setPreviewMarkdown(false);
              }}
            >
              <span>{tab.path.split("/").pop()}</span>
              {tab.dirty && <span className="runtime-files-tab__dot" />}
              <span
                className="runtime-files-tab__close"
                role="button"
                tabIndex={-1}
                onClick={(e) => closeTab(tab.path, e)}
              >
                <X className="h-3 w-3" />
              </span>
            </button>
          ))}
        </div>
      )}

      <div
        className={cn(
          "runtime-files-body",
          treeCollapsed && "runtime-files-body--tree-collapsed"
        )}
      >
        {/* Tree panel */}
        <div
          className={cn(
            "runtime-files-tree",
            treeCollapsed && "runtime-files-tree--collapsed"
          )}
        >
          {workspaceTree.length === 0 ? (
            <div className="runtime-empty">
              <FolderTree className="h-5 w-5" />
              <p>{t("runtime.files.noVisibleFiles")}</p>
            </div>
          ) : (
            renderTreeItems(workspaceTree, 0)
          )}
        </div>

        {/* Editor panel */}
        <div className="runtime-files-editor">
          {fileLoading ? (
            <div className="runtime-empty">
              <LoaderCircle className="h-5 w-5 animate-spin" />
              <p>{t("runtime.files.loadingFile")}</p>
            </div>
          ) : fileError ? (
            <div className="runtime-inline-alert runtime-inline-alert--danger">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{fileError}</span>
            </div>
          ) : activeTab ? (
            <>
              <div className="runtime-files-editor__toolbar">
                <div className="runtime-files-editor__file-info">
                  <span className="runtime-code-inline">{activeTab.path}</span>
                  <span className="text-xs text-[var(--text-quaternary)]">
                    {langLabel}
                  </span>
                </div>
                <div className="runtime-files-editor__toolbar-actions">
                  {/* Markdown preview toggle */}
                  {isMarkdown && !isEditing && (
                    <button
                      type="button"
                      onClick={() => setPreviewMarkdown((p) => !p)}
                      className={cn(
                        "runtime-ghost-button",
                        previewMarkdown && "is-active"
                      )}
                      title={previewMarkdown ? t("runtime.files.sourceCode") : t("common.preview")}
                    >
                      {previewMarkdown ? (
                        <Code2 className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                      {previewMarkdown ? t("common.code") : t("common.preview")}
                    </button>
                  )}

                  {isEditing ? (
                    <>
                      <button
                        type="button"
                        onClick={() => void saveFile()}
                        disabled={saving}
                        className="runtime-ghost-button"
                      >
                        {saving ? (
                          <LoaderCircle className="h-4 w-4 animate-spin" />
                        ) : (
                          <Save className="h-4 w-4" />
                        )}
                        {t("common.save")}
                      </button>
                      <button
                        type="button"
                        onClick={cancelEditing}
                        className="runtime-ghost-button"
                      >
                        {t("common.cancel")}
                      </button>
                    </>
                  ) : canEdit ? (
                    <button
                      type="button"
                      onClick={startEditing}
                      className="runtime-ghost-button"
                    >
                      <Edit3 className="h-4 w-4" />
                      {t("common.edit")}
                    </button>
                  ) : null}
                </div>
              </div>

              {saveError ? (
                <div className="runtime-inline-alert runtime-inline-alert--danger">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{saveError}</span>
                </div>
              ) : null}

              {/* Search overlay */}
              {searchOpen && (
                <div className="runtime-files-search">
                  <Search className="h-3.5 w-3.5" style={{ flexShrink: 0 }} />
                  <input
                    ref={searchInputRef}
                    type="text"
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setCurrentMatchIndex(0);
                    }}
                    onKeyDown={handleSearchKeyDown}
                    placeholder={t("runtime.files.searchPlaceholder")}
                    autoFocus
                  />
                  {searchQuery && (
                    <span className="runtime-files-search__count">
                      {matchCount > 0 ? `${currentMatchIndex + 1}/${matchCount}` : "0/0"}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={closeSearch}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}

              {isTruncated && (
                <div className="runtime-inline-alert">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{t("runtime.files.truncatedFile")}</span>
                </div>
              )}

              {isBinary ? (
                <div className="runtime-inline-alert">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>{t("runtime.files.binaryFile")}</span>
                </div>
              ) : isEditing ? (
                <div className="runtime-files-editor__edit-area">
                  <div className="runtime-files-editor__gutter" ref={gutterRef}>
                    {Array.from({ length: editLineNumbers.count }, (_, i) => (
                      <div key={i} className="runtime-files-gutter__line">{i + 1}</div>
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
                      onChange={(e) => handleEditChange(e.target.value)}
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
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkBreaks]}
                    >
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
                    currentMatchIndex={currentMatchIndex}
                    onMatchCount={handleMatchCount}
                  >
                    {activeTab.content}
                  </SyntaxHighlight>
                </div>
              )}

              {/* Status bar */}
              <div className="runtime-files-statusbar">
                <span>{lineCount} {t("common.lines")}</span>
                <span>{formatBytes(new TextEncoder().encode(activeContent).byteLength)}</span>
                <span>{langLabel}</span>
                <span>UTF-8</span>
                {isEditing && (
                  <span>
                    Ln {cursorLine}, Col {cursorCol}
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="runtime-empty">
              <FolderTree className="h-5 w-5" />
              <p>{t("runtime.files.openFileToView")}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
