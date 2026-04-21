"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Eye,
  MonitorPlay,
  RefreshCcw,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { translate } from "@/lib/i18n";
import { humanizeRuntimeAttachError } from "@/lib/runtime-errors";
import type { RuntimeBrowserState } from "@/lib/runtime-types";
import { buildClientWebSocketUrl, getRuntimeLabel } from "@/lib/runtime-ui";
import { cn } from "@/lib/utils";

type RuntimeMutate = (
  resourcePath: string,
  options?: { searchParams?: URLSearchParams }
) => Promise<Record<string, unknown>>;

type RuntimeFetchResource = <T>(
  resourcePath: string,
  searchParams?: URLSearchParams
) => Promise<T>;

interface BrowserAttachPayload {
  browser?: RuntimeBrowserState;
  relay_snapshot_path?: string | null;
  relay_novnc_path?: string | null;
  error?: string;
}

interface RuntimeBrowserPanelProps {
  agentId: string;
  taskId: number;
  browser: RuntimeBrowserState;
  mutate: RuntimeMutate;
  fetchResource: RuntimeFetchResource;
}

export function RuntimeBrowserPanel({
  agentId,
  taskId,
  browser,
  mutate,
}: RuntimeBrowserPanelProps) {
  const { t } = useAppI18n();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const snapshotSocketRef = useRef<WebSocket | null>(null);
  const rfbRef = useRef<{ disconnect?: () => void } | null>(null);
  const screenshotUrlRef = useRef<string | null>(null);
  const [snapshot, setSnapshot] = useState<RuntimeBrowserState>(browser);
  const [connectionLabel, setConnectionLabel] = useState(() => t("runtime.browser.preparing"));
  const [error, setError] = useState<string | null>(null);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [screenshotError, setScreenshotError] = useState<string | null>(null);
  const isEffectivelyUnavailable =
    snapshot.status === "unavailable" &&
    (Boolean(snapshot.session_persisted_only) || snapshot.visual_available === false);

  const browserPropRef = useRef(browser);
  useEffect(() => {
    browserPropRef.current = browser;
  }, [browser]);

  useEffect(() => {
    setSnapshot((current) => ({ ...current, ...browser }));
  }, [browser]);

  const releaseScreenshot = useCallback(() => {
    if (screenshotUrlRef.current) {
      URL.revokeObjectURL(screenshotUrlRef.current);
      screenshotUrlRef.current = null;
    }
    setScreenshotUrl(null);
  }, []);

  const refreshSnapshot = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/runtime/agents/${agentId}/tasks/${taskId}/browser`,
        { cache: "no-store" }
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const fallback: RuntimeBrowserState = {
          status: "unavailable",
          unavailable_reason: payload?.error || t("runtime.browser.endpointError"),
        };
        setSnapshot((current) => ({ ...current, ...fallback }));
        return fallback;
      }
      const payload = await response.json();
      if (payload.browser) {
        setSnapshot((current) => ({ ...current, ...payload.browser }));
      }
      return payload.browser ?? null;
    } catch {
      return null;
    }
  }, [agentId, taskId, t]);

  const refreshScreenshot = useCallback(async () => {
    if (snapshot.novnc_port != null) {
      releaseScreenshot();
      setScreenshotError(null);
      return false;
    }

    const response = await fetch(
      `/api/runtime/agents/${agentId}/tasks/${taskId}/browser/screenshot?ts=${Date.now()}`,
      {
        cache: "no-store",
      }
    );

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      releaseScreenshot();
      setScreenshotError(
        humanizeBrowserVisualError(
          payload?.error || t("runtime.browser.screenshotUnavailable")
        )
      );
      return false;
    }

    const blob = await response.blob();
    if (!blob.size) {
      releaseScreenshot();
      setScreenshotError(
        t("runtime.browser.invalidImage")
      );
      return false;
    }

    const nextUrl = URL.createObjectURL(blob);
    if (screenshotUrlRef.current) {
      URL.revokeObjectURL(screenshotUrlRef.current);
    }
    screenshotUrlRef.current = nextUrl;
    setScreenshotUrl(nextUrl);
    setScreenshotError(null);
    return true;
  }, [agentId, releaseScreenshot, snapshot.novnc_port, taskId, t]);

  const connectBrowser = useCallback(async () => {
    setError(null);

    const latestSnapshot = (await refreshSnapshot()) ?? browserPropRef.current;
    if (latestSnapshot.novnc_port == null) {
      setConnectionLabel(t("runtime.browser.snapshotMetadata"));
      if (latestSnapshot.status === "unavailable" && latestSnapshot.session_persisted_only) {
        releaseScreenshot();
        setScreenshotError(
          humanizeBrowserVisualError(String(latestSnapshot.unavailable_reason || ""))
        );
        return;
      }
      await refreshScreenshot();
      return;
    }

    setConnectionLabel(t("runtime.browser.preparingAttach"));

    const payload = (await mutate("attach/browser")) as BrowserAttachPayload;

    if (payload.error) {
      throw new Error(payload.error);
    }

    if (payload.browser) {
      setSnapshot(payload.browser);
    }

    snapshotSocketRef.current?.close();
    if (payload.relay_snapshot_path) {
      const socket = new WebSocket(buildClientWebSocketUrl(payload.relay_snapshot_path));
      snapshotSocketRef.current = socket;
      socket.addEventListener("open", () => {
        setConnectionLabel(t("runtime.browser.snapshotActive"));
      });
      socket.addEventListener("message", (event) => {
        try {
          const message = JSON.parse(String(event.data)) as {
            type?: string;
            browser?: RuntimeBrowserState;
          };
          if (message.browser) {
            setSnapshot(message.browser);
          }
        } catch {
          // Ignore malformed frames.
        }
      });
      socket.addEventListener("close", () => {
        setConnectionLabel(t("runtime.browser.snapshotClosed"));
      });
      socket.addEventListener("error", () => {
        setError(t("runtime.browser.snapshotFailure"));
      });
    }

    rfbRef.current?.disconnect?.();
    if (payload.relay_novnc_path && viewportRef.current) {
      const rfbModule = await import("@novnc/novnc/lib/rfb.js");
      const RFB = rfbModule.default;
      const rfb = new RFB(
        viewportRef.current,
        buildClientWebSocketUrl(payload.relay_novnc_path)
      ) as {
        scaleViewport: boolean;
        resizeSession: boolean;
        background: string;
        addEventListener?: (name: string, handler: () => void) => void;
        disconnect?: () => void;
      };

      rfb.scaleViewport = true;
      rfb.resizeSession = false;
      rfb.background = "#0a0a0a";
      rfb.addEventListener?.("connect", () => {
        setConnectionLabel(t("runtime.browser.liveConnected"));
      });
      rfb.addEventListener?.("disconnect", () => {
        setConnectionLabel(t("runtime.browser.liveDisconnected"));
      });
      rfbRef.current = rfb;
    } else {
      setConnectionLabel(t("runtime.browser.noVncFallback"));
    }
  }, [mutate, refreshScreenshot, refreshSnapshot, releaseScreenshot, t]);

  const handleAttachFailure = useCallback(
    async (attachError: unknown) => {
      const rawMessage =
        attachError instanceof Error ? attachError.message : t("runtime.browser.openFailure");

      try {
        const latestSnapshot = await refreshSnapshot();
        if (
          latestSnapshot?.novnc_port == null &&
          !(latestSnapshot?.status === "unavailable" && latestSnapshot.session_persisted_only)
        ) {
          await refreshScreenshot();
        } else if (latestSnapshot?.status === "unavailable") {
          releaseScreenshot();
          setScreenshotError(
            humanizeBrowserVisualError(String(latestSnapshot.unavailable_reason || ""))
          );
        }
        setConnectionLabel(t("runtime.browser.snapshotMetadata"));
        setError(humanizeRuntimeAttachError("browser", rawMessage, "snapshot"));
      } catch {
        setError(rawMessage);
      }
    },
    [refreshScreenshot, refreshSnapshot, releaseScreenshot, t]
  );

  const prevStatusRef = useRef(snapshot.status);
  useEffect(() => {
    const wasUnavailable =
      prevStatusRef.current === "unavailable" || prevStatusRef.current == null;
    const isNowAvailable =
      snapshot.status != null && snapshot.status !== "unavailable";
    prevStatusRef.current = snapshot.status;

    if (wasUnavailable && isNowAvailable) {
      setError(null);
      setScreenshotError(null);
      void connectBrowser().catch((err: unknown) => {
        void handleAttachFailure(err);
      });
    }
  }, [snapshot.status, connectBrowser, handleAttachFailure]);

  useEffect(() => {
    void connectBrowser().catch((attachError: unknown) => {
      void handleAttachFailure(attachError);
    });

    return () => {
      snapshotSocketRef.current?.close();
      rfbRef.current?.disconnect?.();
      releaseScreenshot();
    };
  }, [connectBrowser, handleAttachFailure, releaseScreenshot]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (snapshotSocketRef.current?.readyState !== WebSocket.OPEN) {
        void refreshSnapshot().catch(() => undefined);
      }
      if (snapshot.novnc_port == null && !isEffectivelyUnavailable) {
        void refreshScreenshot().catch(() => undefined);
      }
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, [isEffectivelyUnavailable, refreshScreenshot, refreshSnapshot, snapshot.novnc_port]);

  return (
    <div className="space-y-4">
      <div className="runtime-surface-header">
        <div className="runtime-surface-header__main">
          <span className="runtime-live-badge runtime-live-badge--subtle">
            <span
              className={cn(
                "runtime-live-badge__dot",
                snapshot.status !== "running" && "runtime-live-badge__dot--idle"
              )}
            />
            {connectionLabel}
          </span>
          <div className="runtime-surface-header__title">
            <Eye className="h-4 w-4" />
            <span>{t("runtime.browser.title")}</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            void connectBrowser().catch((attachError: unknown) => {
              void handleAttachFailure(attachError);
            });
          }}
          className="runtime-ghost-button"
        >
          <RefreshCcw className="h-4 w-4" />
          {t("common.reconnect")}
        </button>
      </div>

      <div className="runtime-stat-strip runtime-stat-strip--compact">
        <div className="runtime-stat-strip__item">
          <span className="runtime-stat-strip__label">{t("common.status")}</span>
          <span className="runtime-stat-strip__value">
            {getRuntimeLabel(snapshot.status || "unavailable")}
          </span>
        </div>
        {snapshot.transport ? (
          <div className="runtime-stat-strip__item">
            <span className="runtime-stat-strip__label">{t("common.mode")}</span>
            <span className="runtime-stat-strip__value">{snapshot.transport}</span>
          </div>
        ) : null}
        {snapshot.display_id != null ? (
          <div className="runtime-stat-strip__item">
            <span className="runtime-stat-strip__label">{t("common.display")}</span>
            <span className="runtime-stat-strip__value">:{snapshot.display_id}</span>
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="runtime-inline-alert runtime-inline-alert--danger">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="runtime-browser-shell overflow-hidden">
        <div
          ref={viewportRef}
          className="relative flex h-[52vh] min-h-[420px] items-center justify-center bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.05),transparent_48%),linear-gradient(180deg,#0a0a0a_0%,#050505_100%)]"
        >
          {snapshot.novnc_port == null && screenshotUrl ? (
            <Image
              src={screenshotUrl}
              alt="Browser runtime"
              fill
              unoptimized
              className="object-contain"
            />
          ) : null}

          {snapshot.novnc_port == null && !screenshotUrl ? (
            <div className="runtime-browser-empty mx-auto max-w-md text-center">
              <MonitorPlay className="mx-auto h-8 w-8 text-[var(--text-tertiary)]" />
              <p className="mt-4 text-sm font-semibold text-[var(--text-primary)]">
                {snapshot.status === "unavailable"
                  ? t("runtime.browser.visualSessionUnavailable")
                  : t("runtime.browser.noGraphicsTransport")}
              </p>
              <p className="mt-2 text-sm leading-6 text-[var(--text-tertiary)]">
                {screenshotError ||
                  t("runtime.browser.noVncDescription")}
              </p>
              {snapshot.missing_binaries?.length ? (
                <p className="mt-3 text-xs text-[var(--text-quaternary)]">
                  {t("runtime.browser.missingBinaries")}: {snapshot.missing_binaries.join(", ")}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="runtime-stat-strip">
        <div className="runtime-stat-strip__item">
          <span className="runtime-stat-strip__label">{t("common.visual")}</span>
          <span className="runtime-stat-strip__value">
            {screenshotUrl
              ? t("runtime.browser.activeSnapshot")
              : screenshotError || String(snapshot.unavailable_reason || t("runtime.browser.noVisualSurface"))}
          </span>
        </div>
        <div className="runtime-stat-strip__item">
          <span className="runtime-stat-strip__label">{t("runtime.room.runtimeDir")}</span>
          <span className="runtime-stat-strip__value runtime-code-inline">
            {snapshot.runtime_dir || "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

function humanizeBrowserVisualError(message: string | null | undefined) {
  const normalized = String(message || "").toLowerCase();

  if (normalized.includes("browser is not available")) {
    return translate("runtime.browser.sessionGone");
  }

  if (normalized.includes("browser screenshot unavailable")) {
    return translate("runtime.browser.noScreenshot");
  }

  return message || translate("runtime.browser.noVisualForSession");
}
