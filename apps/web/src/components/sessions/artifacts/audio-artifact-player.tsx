"use client";

import { useMemo, useRef, useState } from "react";
import { Download, Pause, Play } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useArtifactDownload } from "@/hooks/use-artifact-download";
import {
  executionArtifactToArtifactDetail,
  runtimeArtifactDownloadUrl,
  readRuntimeArtifactId,
} from "@/components/sessions/artifacts/artifact-detail";
import { cn } from "@/lib/utils";
import type { ExecutionArtifact } from "@/lib/types";

interface AudioArtifactPlayerProps {
  artifact: ExecutionArtifact;
  agentId?: string | null;
  activityAt?: string | null;
  className?: string;
}

const WAVEFORM = [
  0.24, 0.42, 0.68, 0.35, 0.58, 0.74, 0.9, 0.64, 0.38, 0.72,
  0.48, 0.3, 0.78, 0.92, 0.52, 0.4, 0.67, 0.84, 0.46, 0.62,
  0.76, 0.55, 0.36, 0.69, 0.88, 0.57, 0.44, 0.82, 0.61, 0.34,
  0.7, 0.95, 0.5, 0.39, 0.73, 0.86, 0.59, 0.47, 0.66, 0.31,
] as const;

function formatAudioTime(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "00:00";
  const totalSeconds = Math.floor(value);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function AudioArtifactPlayer({
  artifact,
  agentId,
  activityAt,
  className,
}: AudioArtifactPlayerProps) {
  const { t } = useAppI18n();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const downloader = useArtifactDownload();
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const runtimeArtifactId = readRuntimeArtifactId(artifact);
  const audioUrl = runtimeArtifactDownloadUrl(runtimeArtifactId, agentId);
  const artifactDetail = useMemo(
    () => executionArtifactToArtifactDetail(artifact, agentId, activityAt),
    [activityAt, agentId, artifact],
  );
  const progress = duration > 0 ? Math.min(1, Math.max(0, currentTime / duration)) : 0;
  const label = artifact.label?.trim() || t("sessions.artifacts.audio", undefined);

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio || !audioUrl) {
      setError(t("sessions.artifacts.audioUnavailable", undefined));
      return;
    }
    try {
      if (playing) {
        audio.pause();
        setPlaying(false);
        return;
      }
      await audio.play();
      setPlaying(true);
      setError(null);
    } catch {
      setPlaying(false);
      setError(t("sessions.artifacts.audioLoadError", undefined));
    }
  };

  const visibleTime = duration > 0 ? duration : currentTime;

  return (
    <div
      className={cn(
        "inline-flex w-auto min-w-[220px] max-w-[320px] items-center gap-2 rounded-[var(--radius-chip)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-2 py-1.5 text-[var(--text-primary)] shadow-none",
        className,
      )}
    >
      {audioUrl ? (
        <audio
          ref={audioRef}
          preload="metadata"
          src={audioUrl}
          onLoadedMetadata={(event) => {
            const nextDuration = event.currentTarget.duration;
            if (Number.isFinite(nextDuration)) setDuration(nextDuration);
          }}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onEnded={() => {
            setPlaying(false);
            setCurrentTime(0);
          }}
          onPause={() => setPlaying(false)}
          onPlay={() => setPlaying(true)}
          onError={() => {
            setPlaying(false);
            setError(t("sessions.artifacts.audioLoadError", undefined));
          }}
        />
      ) : null}
      <button
        type="button"
        onClick={() => void togglePlayback()}
        aria-label={
          playing
            ? t("sessions.artifacts.pauseAudio", undefined)
            : t("sessions.artifacts.playAudio", undefined)
        }
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--text-primary)] text-[var(--canvas)] transition-colors hover:bg-[var(--text-secondary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--text-tertiary)]"
      >
        {playing ? (
          <Pause className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
        ) : (
          <Play className="ml-0.5 h-3.5 w-3.5" strokeWidth={2} aria-hidden />
        )}
      </button>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <div
          className="flex h-4 min-w-0 flex-1 items-center gap-[2px]"
          aria-hidden
        >
          {WAVEFORM.map((height, index) => {
            const active = index / WAVEFORM.length <= progress;
            return (
              <span
                key={index}
                className={cn(
                  "w-[2px] rounded-full transition-colors",
                  active ? "bg-[var(--text-primary)]" : "bg-[var(--border-strong)]",
                )}
                style={{ height: `${Math.max(3, height * 14)}px` }}
              />
            );
          })}
        </div>
        <span className="shrink-0 font-mono text-[0.6875rem] leading-none text-[var(--text-tertiary)]">
          {formatAudioTime(visibleTime)}
        </span>
        {artifactDetail ? (
          <button
            type="button"
            onClick={() => void downloader.download(artifactDetail)}
            disabled={downloader.isDownloading}
            aria-label={t("sessions.artifacts.downloadAudio", undefined)}
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-chip)] text-[var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] disabled:opacity-60"
          >
            <Download className="h-3 w-3" strokeWidth={1.75} aria-hidden />
          </button>
        ) : null}
        {error ? (
          <span className="sr-only">{error}</span>
        ) : (
          <span className="sr-only">{label}</span>
        )}
      </div>
    </div>
  );
}
