"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ImageOff,
  X,
} from "lucide-react";
import { useState } from "react";
import { AudioArtifactPlayer } from "@/components/sessions/artifacts/audio-artifact-player";
import { ArtifactViewer } from "@/components/sessions/artifacts/artifact-viewer";
import { formatFileSize, readArtifactFilename } from "@/components/sessions/artifacts/artifact-meta";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useArtifactDownload } from "@/hooks/use-artifact-download";
import type { ArtifactDetail } from "@/lib/contracts/artifacts";
import type { ExecutionArtifact } from "@/lib/types";

export interface ArtifactLightboxItem {
  key: string;
  artifact: ExecutionArtifact;
  detail: ArtifactDetail | null;
  previewUrl: string | null;
  label: string;
  activityAt?: string | null;
}

interface ArtifactLightboxProps {
  items: ArtifactLightboxItem[];
  activeKey: string | null;
  agentId?: string | null;
  onActiveKeyChange: (key: string) => void;
  onOpenChange: (open: boolean) => void;
}

function artifactTitle(item: ArtifactLightboxItem): string {
  return (
    readArtifactFilename(item.artifact) ??
    item.artifact.label ??
    item.detail?.label ??
    item.label
  );
}

function artifactMeta(item: ArtifactLightboxItem): string {
  return [
    item.artifact.kind.toUpperCase(),
    item.artifact.mime_type,
    formatFileSize(item.artifact.size_bytes),
  ]
    .filter(Boolean)
    .join(" · ");
}

export function ArtifactLightbox({
  items,
  activeKey,
  agentId,
  onActiveKeyChange,
  onOpenChange,
}: ArtifactLightboxProps) {
  const { t } = useAppI18n();
  const downloader = useArtifactDownload();
  const [failedPreviewKeys, setFailedPreviewKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const open = Boolean(activeKey && items.length > 0);
  const activeIndex = Math.max(
    0,
    items.findIndex((item) => item.key === activeKey),
  );
  const activeItem = items[activeIndex] ?? null;
  const hasCarousel = items.length > 1;

  const move = (direction: -1 | 1) => {
    if (!activeItem || items.length === 0) return;
    const nextIndex = (activeIndex + direction + items.length) % items.length;
    const next = items[nextIndex];
    if (next) onActiveKeyChange(next.key);
  };

  const markPreviewFailed = (key: string) => {
    setFailedPreviewKeys((current) => {
      if (current.has(key)) return current;
      const next = new Set(current);
      next.add(key);
      return next;
    });
  };

  const renderBody = () => {
    if (!activeItem) return null;

    const src = activeItem.previewUrl ?? activeItem.detail?.download_url ?? null;

    if (
      activeItem.artifact.kind === "image" &&
      src &&
      !failedPreviewKeys.has(activeItem.key)
    ) {
      return (
        // eslint-disable-next-line @next/next/no-img-element -- Runtime artifacts use authenticated proxy URLs.
        <img
          src={src}
          alt={activeItem.label}
          className="max-h-full max-w-full object-contain"
          draggable={false}
          onError={() => markPreviewFailed(activeItem.key)}
        />
      );
    }

    if (activeItem.artifact.kind === "image") {
      return (
        <div className="flex max-w-sm flex-col items-center gap-3 rounded-[var(--radius-panel)] border border-white/10 bg-white/[0.04] px-6 py-5 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-chip)] border border-white/10 bg-white/[0.06] text-white/50">
            <ImageOff className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="space-y-1">
            <p className="text-[0.875rem] font-medium text-white">
              {t("sessions.artifacts.imagePreviewUnavailable", undefined)}
            </p>
            <p className="text-[0.75rem] leading-5 text-white/55">
              {t("sessions.artifacts.imagePreviewUnavailableHint", undefined)}
            </p>
          </div>
        </div>
      );
    }

    if (activeItem.artifact.kind === "video" && src) {
      return (
        <video
          controls
          preload="metadata"
          src={src}
          className="max-h-full max-w-full rounded-[var(--radius-panel-sm)] bg-black"
        />
      );
    }

    if (activeItem.artifact.kind === "audio") {
      return (
        <AudioArtifactPlayer
          artifact={activeItem.artifact}
          agentId={agentId}
          activityAt={activeItem.activityAt ?? null}
          className="max-w-[380px]"
        />
      );
    }

    if (activeItem.detail) {
      return (
        <div className="max-h-full w-full max-w-5xl overflow-hidden rounded-[var(--radius-panel)] border border-[color:var(--border-subtle)] bg-[var(--surface-panel)] shadow-[var(--shadow-soft)]">
          <ArtifactViewer artifact={activeItem.detail} showHeader={false} />
        </div>
      );
    }

    return (
      <div className="rounded-[var(--radius-panel)] border border-[color:var(--border-subtle)] bg-[var(--surface-panel)] px-6 py-5 text-center text-[0.875rem] text-[var(--text-tertiary)]">
        {t("sessions.artifacts.previewUnavailable", undefined)}
      </div>
    );
  };

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onOpenChange(false);
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[90] bg-black/85 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0" />
        <DialogPrimitive.Content
          className="fixed inset-0 z-[91] flex flex-col bg-black/70 text-white outline-none"
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              event.preventDefault();
              move(-1);
            } else if (event.key === "ArrowRight") {
              event.preventDefault();
              move(1);
            }
          }}
        >
          <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-3 sm:px-5">
            <div className="min-w-0">
              <DialogPrimitive.Title className="truncate text-[0.875rem] font-medium text-white">
                {activeItem ? artifactTitle(activeItem) : t("sessions.artifacts.preview", undefined)}
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="truncate font-mono text-[0.6875rem] text-white/45">
                {activeItem
                  ? artifactMeta(activeItem)
                  : t("sessions.artifacts.previewDescription", undefined)}
              </DialogPrimitive.Description>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {activeItem?.detail ? (
                <button
                  type="button"
                  onClick={() => void downloader.download(activeItem.detail as ArtifactDetail)}
                  disabled={downloader.isDownloading}
                  aria-busy={downloader.isDownloading}
                  aria-label={t("sessions.artifacts.download", undefined)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-chip)] bg-transparent text-white/55 transition-colors hover:bg-white/[0.08] hover:text-white disabled:opacity-50"
                >
                  <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                </button>
              ) : null}
              <DialogPrimitive.Close
                aria-label={t("common.close", undefined)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-chip)] bg-transparent text-white/55 transition-colors hover:bg-white/[0.08] hover:text-white"
              >
                <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </DialogPrimitive.Close>
            </div>
          </header>

          {hasCarousel ? (
            <>
              <button
                type="button"
                onClick={() => move(-1)}
                aria-label={t("sessions.artifacts.previous", undefined)}
                style={{
                  position: "fixed",
                  top: "50%",
                  left: "16px",
                  right: "auto",
                  bottom: "auto",
                  transform: "translateY(-50%)",
                  zIndex: 92,
                }}
                className="inline-flex h-9 w-9 items-center justify-center rounded-[var(--radius-chip)] bg-transparent text-white/45 transition-colors hover:bg-white/[0.08] hover:text-white/85"
              >
                <ChevronLeft className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              </button>
              <button
                type="button"
                onClick={() => move(1)}
                aria-label={t("sessions.artifacts.next", undefined)}
                style={{
                  position: "fixed",
                  top: "50%",
                  left: "auto",
                  right: "16px",
                  bottom: "auto",
                  transform: "translateY(-50%)",
                  zIndex: 92,
                }}
                className="inline-flex h-9 w-9 items-center justify-center rounded-[var(--radius-chip)] bg-transparent text-white/45 transition-colors hover:bg-white/[0.08] hover:text-white/85"
              >
                <ChevronRight className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              </button>
            </>
          ) : null}

          <div className="relative flex min-h-0 flex-1 items-center justify-center px-10 py-5 sm:px-16 sm:py-8">
            <div className="flex h-full w-full items-center justify-center">
              {renderBody()}
            </div>
          </div>

          {hasCarousel ? (
            <footer className="pointer-events-none flex h-10 shrink-0 items-center justify-center px-4 text-[0.75rem] text-white/40">
              <span className="px-2 py-1 font-mono">
                {activeIndex + 1} / {items.length}
              </span>
            </footer>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
