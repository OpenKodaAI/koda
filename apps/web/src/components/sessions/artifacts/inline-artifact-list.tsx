"use client";

import { Download, ExternalLink, ImageOff, PlayCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useArtifactDownload } from "@/hooks/use-artifact-download";
import { AudioArtifactPlayer } from "@/components/sessions/artifacts/audio-artifact-player";
import {
  ArtifactLightbox,
  type ArtifactLightboxItem,
} from "@/components/sessions/artifacts/artifact-lightbox";
import {
  executionArtifactDedupeKey,
  executionArtifactToArtifactDetail,
  readRuntimeArtifactId,
  runtimeArtifactDownloadUrl,
} from "@/components/sessions/artifacts/artifact-detail";
import {
  ARTIFACT_KIND_ICON,
  formatFileSize,
  readArtifactFilename,
} from "@/components/sessions/artifacts/artifact-meta";
import { cn, truncateText } from "@/lib/utils";
import type { ExecutionArtifact } from "@/lib/types";

interface InlineArtifactListProps {
  artifacts: ExecutionArtifact[];
  agentId?: string | null;
  activityAt?: string | null;
}

function isRenderableArtifact(artifact: ExecutionArtifact): boolean {
  if (
    artifact.kind === "text" &&
    artifact.source_type === "assistant_response" &&
    !artifact.url &&
    !readRuntimeArtifactId(artifact)
  ) {
    return false;
  }
  return true;
}

function dedupeArtifacts(artifacts: ExecutionArtifact[]) {
  const seen = new Set<string>();
  const result: ExecutionArtifact[] = [];
  for (const artifact of artifacts) {
    if (!isRenderableArtifact(artifact)) continue;
    const key = executionArtifactDedupeKey(artifact);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(artifact);
  }
  return result;
}

function isBrowserReadableUrl(value: string | null | undefined): value is string {
  if (!value) return false;
  return /^(https?:|blob:|data:)/i.test(value) || value.startsWith("/api/");
}

function imageUrl(artifact: ExecutionArtifact, agentId: string | null | undefined) {
  const runtimeUrl = runtimeArtifactDownloadUrl(readRuntimeArtifactId(artifact), agentId);
  if (runtimeUrl) return runtimeUrl;
  if (isBrowserReadableUrl(artifact.preview_image_url)) return artifact.preview_image_url;
  if (isBrowserReadableUrl(artifact.url)) return artifact.url;
  return null;
}

function playableUrl(artifact: ExecutionArtifact, agentId: string | null | undefined) {
  const runtimeUrl = runtimeArtifactDownloadUrl(readRuntimeArtifactId(artifact), agentId);
  if (runtimeUrl) return runtimeUrl;
  return isBrowserReadableUrl(artifact.url) ? artifact.url : null;
}

function previewUrl(artifact: ExecutionArtifact, agentId: string | null | undefined) {
  const runtimeUrl = runtimeArtifactDownloadUrl(readRuntimeArtifactId(artifact), agentId);
  if (artifact.kind === "image") {
    return runtimeUrl || imageUrl(artifact, agentId);
  }
  if (artifact.kind === "video" || artifact.kind === "audio") {
    return runtimeUrl || playableUrl(artifact, agentId);
  }
  return null;
}

function artifactLabel(
  artifact: ExecutionArtifact,
  t: ReturnType<typeof useAppI18n>["t"],
): string {
  return (
    artifact.label ||
    readArtifactFilename(artifact) ||
    t(`sessions.artifacts.kind.${artifact.kind}`, {
      defaultValue: artifact.kind,
    })
  );
}

function artifactMetaLine(artifact: ExecutionArtifact) {
  return [
    artifact.kind.toUpperCase(),
    artifact.mime_type,
    formatFileSize(artifact.size_bytes),
  ]
    .filter(Boolean)
    .join(" · ");
}

function artifactTextPreview(artifact: ExecutionArtifact): string | null {
  const raw =
    typeof artifact.content === "string"
      ? artifact.content
      : artifact.content !== null && artifact.content !== undefined
        ? JSON.stringify(artifact.content, null, 2)
        : artifact.text_content || artifact.summary || artifact.description || null;
  if (!raw) return null;
  const compact = raw.replace(/\s+/g, " ").trim();
  return compact ? truncateText(compact, 112) : null;
}

function externalUrl(artifact: ExecutionArtifact): string | null {
  return artifact.url && /^https?:\/\//i.test(artifact.url) ? artifact.url : null;
}

function artifactDomain(artifact: ExecutionArtifact): string | null {
  if (artifact.domain) return artifact.domain;
  const href = externalUrl(artifact);
  if (!href) return null;
  try {
    return new URL(href).hostname.replace(/^www\./i, "");
  } catch {
    return null;
  }
}

function isTextArtifactKind(kind: ExecutionArtifact["kind"]) {
  return kind === "text" || kind === "code" || kind === "html";
}

function isDataArtifactKind(kind: ExecutionArtifact["kind"]) {
  return kind === "json" || kind === "yaml" || kind === "xml" || kind === "csv" || kind === "tsv";
}

function isDocumentArtifactKind(kind: ExecutionArtifact["kind"]) {
  return kind === "pdf" || kind === "docx" || kind === "spreadsheet";
}

const MEDIA_PREVIEW_STYLE = {
  width: "min(420px, calc(100vw - 56px))",
  aspectRatio: "16 / 10",
};

function buildLightboxItem(
  artifact: ExecutionArtifact,
  agentId: string | null | undefined,
  activityAt: string | null | undefined,
  t: ReturnType<typeof useAppI18n>["t"],
): ArtifactLightboxItem | null {
  const detail = executionArtifactToArtifactDetail(artifact, agentId, activityAt ?? null);
  const mediaUrl = previewUrl(artifact, agentId);
  if (!detail && !mediaUrl) return null;
  return {
    key: executionArtifactDedupeKey(artifact),
    artifact,
    detail,
    previewUrl: mediaUrl,
    label: artifactLabel(artifact, t),
    activityAt,
  };
}

function ArtifactDownloadButton({
  artifact,
  agentId,
  activityAt,
  className,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  className?: string;
}) {
  const { t } = useAppI18n();
  const downloader = useArtifactDownload();
  const artifactDetail = executionArtifactToArtifactDetail(artifact, agentId, activityAt);
  if (!artifactDetail) return null;
  return (
    <button
      type="button"
      onClick={() => void downloader.download(artifactDetail)}
      disabled={downloader.isDownloading}
      aria-label={t("sessions.artifacts.download", { defaultValue: "Download" })}
      className={cn(
        "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-chip)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] disabled:opacity-60",
        className,
      )}
    >
      <Download className="icon-xs" strokeWidth={1.75} aria-hidden />
    </button>
  );
}

function LinkArtifactCard({
  artifact,
  agentId,
  activityAt,
  onOpen,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  onOpen?: () => void;
}) {
  const { t } = useAppI18n();
  const Icon = ARTIFACT_KIND_ICON.url;
  const href = externalUrl(artifact);
  const title = artifact.label || artifact.site_name || artifactDomain(artifact) || href || artifact.id;
  const subtitle = artifact.description || artifact.summary || artifactDomain(artifact) || href;
  const content = (
    <>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-chip)] bg-[var(--panel)] text-[var(--text-tertiary)]">
        <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[0.8125rem] text-[var(--text-primary)]">{title}</span>
        {subtitle ? (
          <span className="truncate text-[0.75rem] text-[var(--text-tertiary)]">
            {subtitle}
          </span>
        ) : null}
      </span>
    </>
  );

  return (
    <div
      data-artifact-kind={artifact.kind}
      data-artifact-visual="link"
      className="flex w-full max-w-[420px] items-center gap-2 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-2.5 py-2"
    >
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          aria-label={t("sessions.context.artifacts.openExternal", {
            defaultValue: "Open external link",
          })}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {content}
        </a>
      ) : (
        <button
          type="button"
          onClick={onOpen}
          disabled={!onOpen}
          aria-label={t("sessions.context.artifacts.openPreview", {
            defaultValue: "Open preview",
          })}
          className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default"
        >
          {content}
        </button>
      )}
      {href ? (
        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]" strokeWidth={1.75} aria-hidden />
      ) : (
        <ArtifactDownloadButton artifact={artifact} agentId={agentId} activityAt={activityAt} />
      )}
    </div>
  );
}

function TextArtifactCard({
  artifact,
  agentId,
  activityAt,
  onOpen,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  onOpen?: () => void;
}) {
  const { t } = useAppI18n();
  const Icon = ARTIFACT_KIND_ICON[artifact.kind];
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const preview = artifactTextPreview(artifact);
  const meta = artifactMetaLine(artifact);

  return (
    <div
      data-artifact-kind={artifact.kind}
      data-artifact-visual={isDataArtifactKind(artifact.kind) ? "data" : "text"}
      className="flex w-full max-w-[420px] items-start gap-2.5 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5"
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={!onOpen}
        className="flex min-w-0 flex-1 items-start gap-2.5 text-left disabled:cursor-default"
        aria-label={t("sessions.context.artifacts.openPreview", {
          defaultValue: "Open preview",
        })}
      >
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-chip)] bg-[var(--panel)] text-[var(--text-tertiary)]">
          <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[0.8125rem] text-[var(--text-primary)]">{filename}</span>
          {preview ? (
            <span className="line-clamp-2 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
              {preview}
            </span>
          ) : null}
          {meta ? (
            <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {meta}
            </span>
          ) : null}
        </span>
      </button>
      <ArtifactDownloadButton artifact={artifact} agentId={agentId} activityAt={activityAt} />
    </div>
  );
}

function FileArtifactCard({
  artifact,
  agentId,
  activityAt,
  onOpen,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  onOpen?: () => void;
}) {
  const { t } = useAppI18n();
  const Icon = ARTIFACT_KIND_ICON[artifact.kind];
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const meta = artifactMetaLine(artifact);
  const visual = isDocumentArtifactKind(artifact.kind) ? "document" : "file";

  return (
    <div
      data-artifact-kind={artifact.kind}
      data-artifact-visual={visual}
      className="flex w-full max-w-[420px] items-center gap-2.5 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2"
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={!onOpen}
        className="flex min-w-0 flex-1 items-center gap-2.5 text-left disabled:cursor-default"
        aria-label={t("sessions.context.artifacts.openPreview", {
          defaultValue: "Open preview",
        })}
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-chip)] bg-[var(--panel)] text-[var(--text-tertiary)]">
          <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[0.8125rem] text-[var(--text-primary)]">{filename}</span>
          {meta ? (
            <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {meta}
            </span>
          ) : null}
        </span>
      </button>
      <ArtifactDownloadButton artifact={artifact} agentId={agentId} activityAt={activityAt} />
    </div>
  );
}

function ImageFallbackCard({
  artifact,
  agentId,
  activityAt,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
}) {
  const { t } = useAppI18n();
  const downloader = useArtifactDownload();
  const artifactDetail = executionArtifactToArtifactDetail(artifact, agentId, activityAt);
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const size = formatFileSize(artifact.size_bytes);
  const meta = [artifact.mime_type, size].filter(Boolean).join(" · ");

  return (
    <div
      data-artifact-kind={artifact.kind}
      data-artifact-visual="image-fallback"
      className="flex max-w-[420px] items-center gap-3 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-chip)] border border-[color:var(--border-subtle)] bg-[var(--panel)] text-[var(--text-quaternary)]">
        <ImageOff className="h-4 w-4" strokeWidth={1.75} aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
          {filename}
        </p>
        <p className="truncate text-[0.75rem] text-[var(--text-tertiary)]">
          {t("sessions.artifacts.imagePreviewUnavailable", {
            defaultValue: "Image preview unavailable",
          })}
        </p>
        {meta ? (
          <p className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
            {meta}
          </p>
        ) : null}
      </div>
      {artifactDetail ? (
        <button
          type="button"
          onClick={() => void downloader.download(artifactDetail)}
          disabled={downloader.isDownloading}
          aria-label={t("sessions.artifacts.download", { defaultValue: "Download" })}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-chip)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] disabled:opacity-60"
        >
          <Download className="icon-xs" strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

function ImageArtifactCard({
  artifact,
  agentId,
  activityAt,
  onOpen,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  onOpen?: () => void;
}) {
  const { t } = useAppI18n();
  const inlineDownloader = useArtifactDownload();
  const [loadFailed, setLoadFailed] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const src = imageUrl(artifact, agentId);
  const artifactDetail = executionArtifactToArtifactDetail(artifact, agentId, activityAt);

  if (!src || loadFailed) {
    return (
      <ImageFallbackCard
        artifact={artifact}
        agentId={agentId}
        activityAt={activityAt}
      />
    );
  }

  const label = artifactLabel(artifact, t);
  const loadingLabel = t("sessions.artifacts.loadingImagePreview", {
    defaultValue: "Loading image preview",
  });

  return (
    <div
      data-inline-image-artifact
      data-artifact-kind={artifact.kind}
      data-artifact-visual="image"
      className={
        imageLoaded
          ? "group relative inline-flex w-fit max-w-full shrink-0 overflow-hidden rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-transparent leading-none"
          : "group relative flex w-full max-w-[420px] overflow-hidden rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)]"
      }
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={!onOpen}
        aria-label={t("sessions.context.artifacts.openPreview", {
          defaultValue: "Open preview",
        })}
        className={
          imageLoaded
            ? "relative inline-flex max-w-full overflow-hidden leading-none disabled:cursor-default"
            : "relative block h-[220px] w-full disabled:cursor-default"
        }
      >
        {!imageLoaded ? (
          <div
            role="status"
            aria-label={loadingLabel}
            className="skeleton h-full w-full rounded-none"
          />
        ) : null}
        {/* eslint-disable-next-line @next/next/no-img-element -- Runtime artifacts use authenticated proxy URLs. */}
        <img
          src={src}
          alt={label}
          className={
            imageLoaded
              ? "block h-full w-full object-cover"
              : "absolute inset-0 h-full w-full object-contain opacity-0"
          }
          style={imageLoaded ? MEDIA_PREVIEW_STYLE : undefined}
          loading="lazy"
          onLoad={() => setImageLoaded(true)}
          onError={() => setLoadFailed(true)}
        />
      </button>
      {artifactDetail ? (
        <button
          type="button"
          onClick={() => void inlineDownloader.download(artifactDetail)}
          disabled={inlineDownloader.isDownloading}
          aria-label={t("sessions.artifacts.download", { defaultValue: "Download" })}
          className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-chip)] bg-black/[0.28] text-white/70 opacity-100 transition-colors hover:bg-white/[0.14] hover:text-white disabled:opacity-50 sm:opacity-0 sm:group-hover:opacity-100"
        >
          <Download className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

function VideoArtifactCard({
  artifact,
  agentId,
  activityAt,
  onOpen,
}: {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  onOpen?: () => void;
}) {
  const { t } = useAppI18n();
  const src = playableUrl(artifact, agentId);
  const filename = readArtifactFilename(artifact) ?? artifact.label ?? artifact.id;
  const meta = artifactMetaLine(artifact);

  if (!src) {
    return (
      <FileArtifactCard
        artifact={artifact}
        agentId={agentId}
        activityAt={activityAt}
        onOpen={onOpen}
      />
    );
  }

  return (
    <div
      data-artifact-kind={artifact.kind}
      data-artifact-visual="video"
      className="group relative inline-flex w-fit max-w-full shrink-0 overflow-hidden rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-transparent leading-none"
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={!onOpen}
        className="relative inline-flex max-w-full overflow-hidden leading-none disabled:cursor-default"
        aria-label={t("sessions.context.artifacts.openPreview", {
          defaultValue: "Open preview",
        })}
      >
        <video
          preload="metadata"
          src={src}
          className="block h-full w-full object-cover"
          style={MEDIA_PREVIEW_STYLE}
        />
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-chip)] bg-black/[0.34] text-white/80 transition-colors group-hover:bg-white/[0.12]">
            <PlayCircle className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          </span>
        </span>
        <span className="pointer-events-none absolute inset-x-0 bottom-0 flex min-w-0 flex-col bg-black/[0.48] px-2.5 py-1.5 text-left">
          <span className="truncate text-[0.75rem] text-white/85">{filename}</span>
          {meta ? (
            <span className="truncate font-mono text-[0.625rem] text-white/45">{meta}</span>
          ) : null}
        </span>
      </button>
      <ArtifactDownloadButton
        artifact={artifact}
        agentId={agentId}
        activityAt={activityAt}
        className="absolute right-2 top-2 bg-black/[0.28] text-white/70 hover:bg-white/[0.14] hover:text-white"
      />
    </div>
  );
}

export function InlineArtifactList({
  artifacts,
  agentId,
  activityAt,
}: InlineArtifactListProps) {
  const { t } = useAppI18n();
  const [activeArtifactKey, setActiveArtifactKey] = useState<string | null>(null);
  const visibleArtifacts = useMemo(() => dedupeArtifacts(artifacts), [artifacts]);
  const lightboxItems = useMemo(
    () =>
      visibleArtifacts
        .map((artifact) => buildLightboxItem(artifact, agentId, activityAt, t))
        .filter((item): item is ArtifactLightboxItem => item !== null),
    [activityAt, agentId, t, visibleArtifacts],
  );
  const lightboxKeys = useMemo(
    () => new Set(lightboxItems.map((item) => item.key)),
    [lightboxItems],
  );

  if (visibleArtifacts.length === 0) return null;

  return (
    <>
      <div className="flex flex-col items-start gap-2">
        {visibleArtifacts.map((artifact) => {
          const key = executionArtifactDedupeKey(artifact);
          const canPreview = lightboxKeys.has(key);
          const openPreview = canPreview ? () => setActiveArtifactKey(key) : undefined;

          if (artifact.kind === "audio") {
            return (
              <AudioArtifactPlayer
                key={key}
                artifact={artifact}
                agentId={agentId}
                activityAt={activityAt}
              />
            );
          }

          if (artifact.kind === "image") {
            return (
              <ImageArtifactCard
                key={key}
                artifact={artifact}
                agentId={agentId}
                activityAt={activityAt}
                onOpen={openPreview}
              />
            );
          }

          if (artifact.kind === "video") {
            return (
              <VideoArtifactCard
                key={key}
                artifact={artifact}
                agentId={agentId}
                activityAt={activityAt}
                onOpen={openPreview}
              />
            );
          }

          if (artifact.kind === "url") {
            return (
              <LinkArtifactCard
                key={key}
                artifact={artifact}
                agentId={agentId}
                activityAt={activityAt}
                onOpen={openPreview}
              />
            );
          }

          if (isTextArtifactKind(artifact.kind) || isDataArtifactKind(artifact.kind)) {
            return (
              <TextArtifactCard
                key={key}
                artifact={artifact}
                agentId={agentId}
                activityAt={activityAt}
                onOpen={openPreview}
              />
            );
          }

          return (
            <FileArtifactCard
              key={key}
              artifact={artifact}
              agentId={agentId}
              activityAt={activityAt}
              onOpen={openPreview}
            />
          );
        })}
      </div>
      <ArtifactLightbox
        items={lightboxItems}
        activeKey={activeArtifactKey}
        agentId={agentId}
        onActiveKeyChange={setActiveArtifactKey}
        onOpenChange={(open) => {
          if (!open) setActiveArtifactKey(null);
        }}
      />
    </>
  );
}
