"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { SearchAddon } from "@xterm/addon-search";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { WebglAddon } from "@xterm/addon-webgl";
import { Terminal, type ITheme } from "@xterm/xterm";
import { AlertTriangle, MonitorSmartphone, Search, TerminalSquare, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { humanizeRuntimeAttachError } from "@/lib/runtime-errors";
import type { RuntimeAttachSession, RuntimeTerminal } from "@/lib/runtime-types";
import { buildClientWebSocketUrl } from "@/lib/runtime-ui";
import { cn } from "@/lib/utils";

type RuntimeMutate = (
  resourcePath: string,
  options?: { searchParams?: URLSearchParams }
) => Promise<Record<string, unknown>>;

type RuntimeFetchResource = <T>(
  resourcePath: string,
  searchParams?: URLSearchParams
) => Promise<T>;

interface TerminalAttachPayload {
  attach?: RuntimeAttachSession;
  terminal?: RuntimeTerminal;
  relay_path?: string;
  error?: string;
}

interface RuntimeTerminalPanelProps {
  taskId: number;
  terminals: RuntimeTerminal[];
  mutate: RuntimeMutate;
  fetchResource: RuntimeFetchResource;
}

function readCssVar(
  getPropertyValue: (propertyName: string) => string,
  propertyName: string,
  fallback: string
) {
  const value = getPropertyValue(propertyName).trim();
  return value || fallback;
}

export function buildRuntimeTerminalTheme(
  getPropertyValue: (propertyName: string) => string
): ITheme {
  return {
    background: readCssVar(getPropertyValue, "--terminal-background", "#0a0a0b"),
    foreground: readCssVar(getPropertyValue, "--terminal-foreground", "#f5f3eb"),
    cursor: readCssVar(getPropertyValue, "--terminal-cursor", "#ff4a00"),
    cursorAccent: readCssVar(getPropertyValue, "--terminal-cursor-accent", "#0a0a0b"),
    selectionBackground: readCssVar(
      getPropertyValue,
      "--terminal-selection-background",
      "rgba(255, 74, 0, 0.15)"
    ),
    selectionForeground: readCssVar(
      getPropertyValue,
      "--terminal-selection-foreground",
      "#f5f3eb"
    ),
    scrollbarSliderBackground: readCssVar(
      getPropertyValue,
      "--terminal-scrollbar",
      "rgba(255, 255, 255, 0.06)"
    ),
    scrollbarSliderHoverBackground: readCssVar(
      getPropertyValue,
      "--terminal-scrollbar-hover",
      "rgba(255, 255, 255, 0.12)"
    ),
    scrollbarSliderActiveBackground: readCssVar(
      getPropertyValue,
      "--terminal-scrollbar-active",
      "rgba(255, 255, 255, 0.18)"
    ),
    black: readCssVar(getPropertyValue, "--terminal-black", "#1e1e20"),
    red: readCssVar(getPropertyValue, "--terminal-red", "#f87171"),
    green: readCssVar(getPropertyValue, "--terminal-green", "#69c48a"),
    yellow: readCssVar(getPropertyValue, "--terminal-yellow", "#fbbf24"),
    blue: readCssVar(getPropertyValue, "--terminal-blue", "#60a5fa"),
    magenta: readCssVar(getPropertyValue, "--terminal-magenta", "#c084fc"),
    cyan: readCssVar(getPropertyValue, "--terminal-cyan", "#22d3ee"),
    white: readCssVar(getPropertyValue, "--terminal-white", "#d4d4d8"),
    brightBlack: readCssVar(getPropertyValue, "--terminal-bright-black", "#52525b"),
    brightRed: readCssVar(getPropertyValue, "--terminal-bright-red", "#fca5a5"),
    brightGreen: readCssVar(getPropertyValue, "--terminal-bright-green", "#86efac"),
    brightYellow: readCssVar(getPropertyValue, "--terminal-bright-yellow", "#fde68a"),
    brightBlue: readCssVar(getPropertyValue, "--terminal-bright-blue", "#93c5fd"),
    brightMagenta: readCssVar(getPropertyValue, "--terminal-bright-magenta", "#d8b4fe"),
    brightCyan: readCssVar(getPropertyValue, "--terminal-bright-cyan", "#67e8f9"),
    brightWhite: readCssVar(getPropertyValue, "--terminal-bright-white", "#fafafa"),
  };
}

export function getRuntimeTerminalTheme(): ITheme {
  if (typeof document === "undefined") {
    return buildRuntimeTerminalTheme(() => "");
  }

  return buildRuntimeTerminalTheme((propertyName) =>
    getComputedStyle(document.documentElement).getPropertyValue(propertyName)
  );
}

function applyRuntimeTerminalTheme(terminal: Terminal) {
  const theme = getRuntimeTerminalTheme();
  const options = terminal.options as { theme?: ITheme } | undefined;
  if (options) {
    options.theme = theme;
  }

  if (typeof terminal.refresh === "function") {
    terminal.refresh(0, Math.max(terminal.rows - 1, 0));
  }
}

function pickPreferredTerminal(items: RuntimeTerminal[]) {
  const interactive = items.filter((item) => Boolean(item.interactive));
  return interactive.at(-1) ?? items.at(-1) ?? null;
}

function getTerminalButtonLabel(
  terminal: RuntimeTerminal,
  items: RuntimeTerminal[]
) {
  const baseLabel = terminal.label || `Terminal ${terminal.id}`;
  const matching = items.filter((item) => (item.label || "") === (terminal.label || ""));

  if (matching.length <= 1 || !terminal.label) {
    return baseLabel;
  }

  const index = matching.findIndex((item) => item.id === terminal.id);
  return `${baseLabel} ${index + 1}`;
}

export function RuntimeTerminalPanel({
  taskId,
  terminals,
  mutate,
  fetchResource,
}: RuntimeTerminalPanelProps) {
  const { t } = useAppI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const searchAddonRef = useRef<SearchAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const allowWriteRef = useRef(false);
  const suppressNextAutoConnectRef = useRef(false);
  const [selectedTerminalId, setSelectedTerminalId] = useState<number | null>(
    () => pickPreferredTerminal(terminals)?.id ?? null
  );
  const [connectionLabel, setConnectionLabel] = useState(() => t("runtime.terminal.connecting"));
  const [error, setError] = useState<string | null>(null);
  const [writeMode, setWriteMode] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const terminalOptions = useMemo(
    () =>
      terminals.length > 0
        ? terminals
        : [
            {
              id: -1,
              task_id: taskId,
              label: "Operador",
              terminal_kind: "operator",
              interactive: true,
            } satisfies RuntimeTerminal,
          ],
    [taskId, terminals]
  );
  const effectiveSelectedTerminalId = useMemo(() => {
    if (selectedTerminalId && terminalOptions.some((item) => item.id === selectedTerminalId)) {
      return selectedTerminalId;
    }
    return pickPreferredTerminal(terminalOptions)?.id ?? null;
  }, [selectedTerminalId, terminalOptions]);

  const getSelectedTerminal = useCallback(
    (items: RuntimeTerminal[]) => {
      if (effectiveSelectedTerminalId && effectiveSelectedTerminalId > 0) {
        return (
          items.find((item) => item.id === effectiveSelectedTerminalId) ??
          pickPreferredTerminal(items)
        );
      }

      return pickPreferredTerminal(items);
    },
    [effectiveSelectedTerminalId]
  );

  const writePreview = useCallback((preview: string | null | undefined, label: string) => {
    const terminal = terminalRef.current;
    if (!terminal) return;

    terminal.reset();
    terminal.writeln(label);
    if (preview) {
      terminal.write(preview);
      return;
    }
    terminal.writeln(t("runtime.terminal.noOutputYet"));
  }, [t]);

  const loadPreview = useCallback(async () => {
    const payload = await fetchResource<{ items?: RuntimeTerminal[] }>("terminals");
    const items = payload.items ?? [];
    const selected = getSelectedTerminal(items);

    writePreview(
      selected?.preview,
      t("runtime.terminal.previewHeader")
    );
    setConnectionLabel(t("runtime.terminal.previewMode"));
    return Boolean(selected);
  }, [fetchResource, getSelectedTerminal, t, writePreview]);

  useEffect(() => {
    // Resolve CSS variable to actual font name — WebGL/canvas renderers
    // cannot resolve CSS custom properties, only the CSS engine can.
    const resolved = typeof document !== "undefined"
      ? getComputedStyle(document.documentElement).getPropertyValue("--font-jetbrains").trim()
      : "";
    const fontFamily = resolved
      ? `${resolved}, 'JetBrains Mono', monospace`
      : "'JetBrains Mono', monospace";

    const terminal = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      cursorInactiveStyle: "outline",
      convertEol: true,
      fontFamily,
      fontSize: 13,
      lineHeight: 1.2,
      letterSpacing: 0,
      scrollback: 5000,
      allowProposedApi: true,
      theme: getRuntimeTerminalTheme(),
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => fitAddon.fit())
        : null;
    const syncTheme = () => {
      applyRuntimeTerminalTheme(terminal);
    };

    if (containerRef.current) {
      terminal.open(containerRef.current);

      // Unicode11 first — affects text measurement
      const unicode11 = new Unicode11Addon();
      terminal.loadAddon(unicode11);
      terminal.unicode.activeVersion = "11";

      // WebLinks — clickable URLs
      terminal.loadAddon(
        new WebLinksAddon((_event, uri) => {
          window.open(uri, "_blank", "noopener,noreferrer");
        })
      );

      // Search
      const searchAddon = new SearchAddon();
      terminal.loadAddon(searchAddon);
      searchAddonRef.current = searchAddon;

      // WebGL — GPU-accelerated rendering with graceful fallback
      try {
        const webgl = new WebglAddon();
        webgl.onContextLoss(() => {
          webgl.dispose();
        });
        terminal.loadAddon(webgl);
      } catch {
        // Falls back to canvas renderer
      }

      fitAddon.fit();
      terminal.focus();
      terminal.writeln(t("runtime.terminal.waitingAttach"));
    }

    syncTheme();

    if (containerRef.current && observer) {
      observer.observe(containerRef.current);
    }

    const disposable = terminal.onData((data) => {
      if (allowWriteRef.current && socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(data);
      }
    });

    let themeObserver: MutationObserver | null = null;
    let mediaQuery: MediaQueryList | null = null;
    const mediaListener = () => syncTheme();

    if (typeof MutationObserver !== "undefined") {
      themeObserver = new MutationObserver(syncTheme);
      themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["class", "data-theme"],
      });
    }

    mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)") ?? null;
    if (mediaQuery) {
      mediaQuery.addEventListener("change", mediaListener);
    }

    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;

    return () => {
      themeObserver?.disconnect();
      if (mediaQuery) {
        mediaQuery.removeEventListener("change", mediaListener);
      }
      observer?.disconnect();
      disposable.dispose();
      socketRef.current?.close();
      terminal.dispose();
    };
  }, [t]);

  // Ctrl+F / Cmd+F keybinding
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        const target = e.target as HTMLElement | null;
        const isInTerminal =
          target?.closest?.(".runtime-terminal-shell") ||
          target?.closest?.(".xterm");
        if (isInTerminal) {
          e.preventDefault();
          setSearchOpen(true);
        }
      }
      if (e.key === "Escape" && searchOpen) {
        setSearchOpen(false);
        setSearchQuery("");
        terminalRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [searchOpen]);

  const connectTerminal = useCallback(async (enableWrite: boolean) => {
    const terminal = terminalRef.current;
    if (!terminal) return;

    const searchParams = new URLSearchParams();
    searchParams.set("write", enableWrite ? "true" : "false");

    if (effectiveSelectedTerminalId && effectiveSelectedTerminalId > 0) {
      searchParams.set("terminal_id", String(effectiveSelectedTerminalId));
    }

    setConnectionLabel(
      enableWrite ? t("runtime.terminal.assumeControl") : t("runtime.terminal.enterReadMode")
    );
    setError(null);
    allowWriteRef.current = enableWrite;

    const payload = (await mutate("attach/terminal", {
      searchParams,
    })) as TerminalAttachPayload;

    if (payload.error || !payload.relay_path) {
      throw new Error(payload.error || t("runtime.terminal.attachUnavailable"));
    }

    if (payload.terminal?.id) {
      suppressNextAutoConnectRef.current = payload.terminal.id !== effectiveSelectedTerminalId;
      setSelectedTerminalId(payload.terminal.id);
    }

    setWriteMode(Boolean(payload.attach?.can_write));

    socketRef.current?.close();
    terminal.reset();
    terminal.writeln(
      payload.attach?.can_write
        ? t("runtime.terminal.writeChannelActive")
        : t("runtime.terminal.readChannelActive")
    );

    const socket = new WebSocket(buildClientWebSocketUrl(payload.relay_path));
    socketRef.current = socket;

    socket.addEventListener("open", () => {
      setConnectionLabel(t("runtime.terminal.live"));
      terminal.focus();
      fitAddonRef.current?.fit();
    });

    socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(String(event.data)) as {
          type?: string;
          data?: string;
        };
        if (message.type === "chunk" && message.data) {
          terminal.write(message.data);
        }
        if (message.type === "closed") {
          terminal.writeln(`\r\n${t("runtime.terminal.terminated")}`);
          setConnectionLabel(t("runtime.terminal.terminated"));
        }
      } catch {
        terminal.writeln(`\r\n${t("runtime.terminal.invalidFrame")}`);
      }
    });

    socket.addEventListener("close", () => {
      setConnectionLabel(t("runtime.terminal.channelClosed"));
    });

    socket.addEventListener("error", () => {
      setError(t("runtime.terminal.relayFailure"));
      setConnectionLabel(t("runtime.terminal.terminalError"));
    });
  }, [effectiveSelectedTerminalId, mutate, t]);

  const handleAttachFailure = useCallback(
    async (attachError: unknown) => {
      const rawMessage =
        attachError instanceof Error ? attachError.message : t("runtime.terminal.connectFailure");

      try {
        const hasPreview = await loadPreview();
        setError(
          hasPreview
            ? humanizeRuntimeAttachError("terminal", rawMessage, "preview")
            : rawMessage
        );
      } catch {
        setError(rawMessage);
        setConnectionLabel(t("runtime.terminal.terminalError"));
      }
    },
    [loadPreview, t]
  );

  useEffect(() => {
    let cancelled = false;
    const enqueue =
      typeof queueMicrotask === "function"
        ? queueMicrotask
        : (callback: () => void) => {
            void Promise.resolve().then(callback);
          };

    enqueue(() => {
      if (cancelled) return;
      if (suppressNextAutoConnectRef.current) {
        suppressNextAutoConnectRef.current = false;
        return;
      }
      void connectTerminal(false).catch((attachError: unknown) => {
        void handleAttachFailure(attachError);
      });
    });

    return () => {
      cancelled = true;
    };
  }, [connectTerminal, handleAttachFailure, effectiveSelectedTerminalId]);

  useEffect(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      return undefined;
    }

    const interval = window.setInterval(() => {
      if (socketRef.current?.readyState === WebSocket.OPEN) return;
      void loadPreview().catch(() => undefined);
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadPreview]);

  return (
    <div>
      <div className="runtime-terminal-shell">
        <div className="runtime-terminal-header">
          <div className="runtime-terminal-header__left">
            <span
              className={cn(
                "runtime-live-badge__dot",
                connectionLabel !== t("runtime.terminal.live") && "runtime-live-badge__dot--idle"
              )}
            />
            <TerminalSquare className="h-3.5 w-3.5" />
            <span>{connectionLabel}</span>
          </div>
          <div className="runtime-terminal-header__right">
            {terminalOptions.length > 1 &&
              terminalOptions.map((terminal) => (
                <button
                  key={terminal.id}
                  type="button"
                  onClick={() => setSelectedTerminalId(terminal.id)}
                  className={cn(
                    "runtime-filter-pill",
                    terminal.id === effectiveSelectedTerminalId && "is-active"
                  )}
                >
                  {getTerminalButtonLabel(terminal, terminalOptions)}
                </button>
              ))}
            <button
              type="button"
              onClick={() => {
                void connectTerminal(!writeMode).catch((attachError: unknown) => {
                  void handleAttachFailure(attachError);
                });
              }}
              className={cn("runtime-ghost-button", writeMode && "is-active")}
            >
              <MonitorSmartphone className="h-3.5 w-3.5" />
              {writeMode ? t("runtime.terminal.control") : t("runtime.terminal.read")}
            </button>
          </div>
        </div>

        {searchOpen && (
          <div className="runtime-terminal-search">
            <Search className="h-3 w-3" style={{ color: "var(--text-tertiary)" }} />
            <input
              autoFocus
              placeholder={t("runtime.terminal.searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                if (e.target.value) {
                  searchAddonRef.current?.findNext(e.target.value);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  if (e.shiftKey) {
                    searchAddonRef.current?.findPrevious(searchQuery);
                  } else {
                    searchAddonRef.current?.findNext(searchQuery);
                  }
                }
                if (e.key === "Escape") {
                  setSearchOpen(false);
                  setSearchQuery("");
                  terminalRef.current?.focus();
                }
              }}
            />
            <button
              type="button"
              onClick={() => {
                setSearchOpen(false);
                setSearchQuery("");
                terminalRef.current?.focus();
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}

        <div
          ref={containerRef}
          className="runtime-terminal h-[52vh] min-h-[420px] w-full"
        />
      </div>

      {error ? (
        <div className="runtime-inline-alert runtime-inline-alert--danger mt-4">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  );
}
