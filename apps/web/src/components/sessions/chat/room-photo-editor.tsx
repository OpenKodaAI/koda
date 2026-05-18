"use client";

import {
  type ChangeEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Camera, ImageOff, Loader2, RotateCcw, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

const IDLE_PX = 80;
const CROP_PX = 192;
const OUTPUT_PX = 512;
const OUTPUT_QUALITY = 0.88;

interface RoomPhotoEditorProps {
  threadId: string;
  currentPhotoUrl: string | null;
  /** Solid background applied behind the initials when no image is set. */
  background: string;
  /** Two-letter (or "·") initials displayed when no photo is set. */
  initials: string;
  /** Called after a successful upload. The parent should invalidate caches. */
  onUploaded: (result: { photoUrl: string; photoHash?: string }) => void;
  /** Called after a successful removal. */
  onRemoved: () => void;
}

interface LoadedImage {
  source: HTMLImageElement;
  intrinsicWidth: number;
  intrinsicHeight: number;
}

export function RoomPhotoEditor({
  threadId,
  currentPhotoUrl,
  background,
  initials,
  onUploaded,
  onRemoved,
}: RoomPhotoEditorProps) {
  const { t } = useAppI18n();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [picked, setPicked] = useState<LoadedImage | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The minimum zoom needed to fully cover the square preview at the picked
  // image's aspect ratio. Anything below would expose a transparent gutter.
  const minZoom = useMemo(() => {
    if (!picked) return 1;
    const longest = Math.max(picked.intrinsicWidth, picked.intrinsicHeight);
    const shortest = Math.min(picked.intrinsicWidth, picked.intrinsicHeight);
    return longest / shortest;
  }, [picked]);

  const maxZoom = minZoom * 4;
  const zoomPct =
    maxZoom > minZoom ? ((zoom - minZoom) / (maxZoom - minZoom)) * 100 : 0;

  const clampOffset = useCallback(
    (next: { x: number; y: number }, zoomValue: number, image: LoadedImage) => {
      const drawWidth = image.intrinsicWidth * zoomValue;
      const drawHeight = image.intrinsicHeight * zoomValue;
      const halfDx = Math.max(0, (drawWidth - CROP_PX) / 2);
      const halfDy = Math.max(0, (drawHeight - CROP_PX) / 2);
      const imageScale = CROP_PX / Math.min(image.intrinsicWidth, image.intrinsicHeight);
      const scale = imageScale * (1 / zoomValue);
      return {
        x: Math.max(-halfDx * scale, Math.min(halfDx * scale, next.x)),
        y: Math.max(-halfDy * scale, Math.min(halfDy * scale, next.y)),
      };
    },
    [],
  );

  useEffect(() => {
    if (!picked) return;
    setZoom(minZoom);
    setOffset({ x: 0, y: 0 });
  }, [picked, minZoom]);

  // Reset broken-image state if the URL changes (e.g. after a successful upload).
  useEffect(() => {
    setImgError(false);
  }, [currentPhotoUrl]);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (!file.type.startsWith("image/")) {
        setError(
          t("sessions.room.photo.invalidType", {
            defaultValue: "That file isn't an image.",
          }),
        );
        return;
      }
      try {
        const url = URL.createObjectURL(file);
        const image = new Image();
        image.decoding = "async";
        image.src = url;
        await image.decode().catch(() => {
          return new Promise<void>((resolve, reject) => {
            image.onload = () => resolve();
            image.onerror = () => reject(new Error("decode failed"));
          });
        });
        setPicked({
          source: image,
          intrinsicWidth: image.naturalWidth || image.width,
          intrinsicHeight: image.naturalHeight || image.height,
        });
      } catch {
        setError(
          t("sessions.room.photo.decodeFailed", {
            defaultValue: "Could not read this image.",
          }),
        );
      }
    },
    [t],
  );

  const handleFileChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) void handleFile(file);
      event.target.value = "";
    },
    [handleFile],
  );

  const handlePick = useCallback(() => {
    if (busy || removing) return;
    fileInputRef.current?.click();
  }, [busy, removing]);

  const handleResetCrop = useCallback(() => {
    setZoom(minZoom);
    setOffset({ x: 0, y: 0 });
  }, [minZoom]);

  // Drag-to-pan the visible square across the underlying image.
  const dragRef = useRef<{
    startClientX: number;
    startClientY: number;
    startOffset: { x: number; y: number };
  } | null>(null);

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (!picked) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      dragRef.current = {
        startClientX: event.clientX,
        startClientY: event.clientY,
        startOffset: { ...offset },
      };
    },
    [offset, picked],
  );

  const handlePointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (!picked || !dragRef.current) return;
      const dx = event.clientX - dragRef.current.startClientX;
      const dy = event.clientY - dragRef.current.startClientY;
      const shortest = Math.min(picked.intrinsicWidth, picked.intrinsicHeight);
      const previewToImage = shortest / CROP_PX / zoom;
      const proposed = {
        x: dragRef.current.startOffset.x - dx * previewToImage,
        y: dragRef.current.startOffset.y - dy * previewToImage,
      };
      setOffset(clampOffset(proposed, zoom, picked));
    },
    [clampOffset, picked, zoom],
  );

  const handlePointerUp = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      dragRef.current = null;
    },
    [],
  );

  const handleZoomChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const next = Number.parseFloat(event.target.value);
      if (!Number.isFinite(next) || !picked) return;
      const clamped = Math.max(minZoom, Math.min(next, maxZoom));
      setZoom(clamped);
      setOffset((prev) => clampOffset(prev, clamped, picked));
    },
    [clampOffset, maxZoom, minZoom, picked],
  );

  const handleCancelPick = useCallback(() => {
    setPicked(null);
    setError(null);
  }, []);

  const handleUpload = useCallback(async () => {
    if (!picked || busy) return;
    setBusy(true);
    setError(null);
    try {
      const blob = await renderCroppedJpeg(picked, zoom, offset);
      const formData = new FormData();
      formData.append("photo", blob, "room-photo.jpg");
      const response = await fetch(
        `/api/control-plane/dashboard/squads/threads/${encodeURIComponent(threadId)}/photo`,
        { method: "POST", body: formData, cache: "no-store" },
      );
      if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try {
          const data = (await response.json()) as { error?: string };
          if (data?.error) message = data.error;
        } catch {
          // ignore non-JSON error body
        }
        throw new Error(message);
      }
      const data = (await response.json()) as {
        photoUrl: string;
        photoHash?: string;
      };
      setPicked(null);
      onUploaded({ photoUrl: data.photoUrl, photoHash: data.photoHash });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }, [busy, offset, onUploaded, picked, threadId, zoom]);

  const handleRemove = useCallback(
    async (event?: React.MouseEvent) => {
      event?.stopPropagation();
      if (removing) return;
      setRemoving(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/control-plane/dashboard/squads/threads/${encodeURIComponent(threadId)}/photo`,
          { method: "DELETE", cache: "no-store" },
        );
        if (!response.ok && response.status !== 404) {
          throw new Error(`${response.status} ${response.statusText}`);
        }
        onRemoved();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Remove failed");
      } finally {
        setRemoving(false);
      }
    },
    [onRemoved, removing, threadId],
  );

  const isCropping = picked !== null;
  const sizePx = isCropping ? CROP_PX : IDLE_PX;
  const showImage = !isCropping && Boolean(currentPhotoUrl) && !imgError;
  const showRemoveBadge =
    !isCropping && Boolean(currentPhotoUrl) && !busy;

  return (
    <div className="flex flex-col items-center gap-3">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* The avatar IS the picker. Hover/busy states live on this surface. */}
      <div
        className="relative"
        style={{
          width: sizePx,
          height: sizePx,
          transition:
            "width 200ms var(--ease-out-quart), height 200ms var(--ease-out-quart)",
        }}
      >
        <button
          type="button"
          onClick={isCropping ? undefined : handlePick}
          onPointerDown={isCropping ? handlePointerDown : undefined}
          onPointerMove={isCropping ? handlePointerMove : undefined}
          onPointerUp={isCropping ? handlePointerUp : undefined}
          onPointerCancel={isCropping ? handlePointerUp : undefined}
          disabled={busy || removing}
          aria-label={
            isCropping
              ? t("sessions.room.photo.crop", { defaultValue: "Adjust photo" })
              : currentPhotoUrl
                ? t("sessions.room.photo.replace", {
                    defaultValue: "Replace photo",
                  })
                : t("sessions.room.photo.pick", {
                    defaultValue: "Choose photo",
                  })
          }
          className={cn(
            "group relative flex h-full w-full items-center justify-center overflow-hidden rounded-full border-0 p-0 outline-none",
            "ring-1 ring-[color:var(--border-subtle)]",
            "transition-[box-shadow,transform] duration-[200ms] ease-[var(--ease-out-quart)]",
            !isCropping && !busy && !removing && "cursor-pointer hover:ring-[color:var(--border-strong)] focus-visible:ring-2 focus-visible:ring-[color:var(--accent)]",
            isCropping && "cursor-grab active:cursor-grabbing select-none touch-none",
            (busy || removing) && "cursor-wait",
          )}
          style={{ background }}
        >
          {isCropping && picked ? (
            <CropCanvas image={picked} zoom={zoom} offset={offset} />
          ) : showImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={currentPhotoUrl ?? ""}
              alt=""
              className="h-full w-full object-cover"
              referrerPolicy="no-referrer"
              onError={() => setImgError(true)}
            />
          ) : (
            <span className="font-mono text-[1.5rem] font-medium text-[color:rgba(255,255,255,0.85)]">
              {imgError ? (
                <ImageOff className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              ) : (
                initials
              )}
            </span>
          )}

          {/* Hover affordance: subtle dim + camera icon. Hidden while cropping. */}
          {!isCropping ? (
            <span
              className={cn(
                "pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 text-white/0 transition-[background-color,color] duration-[160ms] ease-[var(--ease-out-quart)]",
                !busy && !removing && "group-hover:bg-black/40 group-hover:text-white group-focus-visible:bg-black/40 group-focus-visible:text-white",
              )}
            >
              <Camera
                className="h-4 w-4 transition-transform duration-[160ms] ease-[var(--ease-out-quart)] group-hover:scale-110"
                strokeWidth={1.75}
                aria-hidden
              />
            </span>
          ) : null}

          {/* Busy overlay (upload in progress). */}
          {busy ? (
            <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/55 text-white">
              <Loader2 className="h-5 w-5 animate-spin" strokeWidth={2} aria-hidden />
            </span>
          ) : null}
        </button>

        {/* Minimalist corner remove. Sits on top of the avatar — only visible
            when there's an actual photo to remove and we're not cropping.
            Position is set inline because the global `:where(button, ...)` rule
            in `globals.css` (unlayered) shadows Tailwind's layered `.absolute`
            utility on every button; inline style wins regardless of cascade. */}
        {showRemoveBadge ? (
          <button
            type="button"
            onClick={(event) => void handleRemove(event)}
            disabled={removing}
            aria-label={t("sessions.room.photo.remove", {
              defaultValue: "Remove photo",
            })}
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full",
              "border border-[color:var(--border-strong)] bg-[var(--panel-strong)] text-[var(--text-tertiary)]",
              "shadow-[var(--shadow-xs)] outline-none",
              "transition-[background-color,color,border-color] duration-[160ms] ease-[var(--ease-out-quart)]",
              "hover:bg-[var(--tone-danger-bg)] hover:text-[var(--tone-danger-dot)] hover:border-[color:var(--tone-danger-border)]",
              "focus-visible:ring-2 focus-visible:ring-[color:var(--accent)]",
              "disabled:cursor-wait disabled:opacity-80",
            )}
            style={{
              position: "absolute",
              top: -4,
              right: -4,
              transform: "translateZ(0)",
            }}
          >
            {removing ? (
              <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2} aria-hidden />
            ) : (
              <Trash2 className="h-3 w-3" strokeWidth={1.75} aria-hidden />
            )}
          </button>
        ) : null}
      </div>

      {/* Crop controls (zoom + reset/cancel/upload) only while cropping. */}
      {isCropping ? (
        <>
          <input
            type="range"
            min={minZoom}
            max={maxZoom}
            step={0.01}
            value={zoom}
            onChange={handleZoomChange}
            aria-label={t("sessions.room.photo.zoom", { defaultValue: "Zoom" })}
            className="ui-slider w-full max-w-[20rem]"
            style={{
              // Inline height + background overrides the global
              // `input[type="range"]` rules. Using `--text-primary` for the
              // filled portion and `--border-strong` for the track so the bar
              // reads clearly against the dark canvas — the global `.ui-slider`
              // border alone wasn't enough contrast for this small overlay.
              height: 8,
              background: `linear-gradient(to right, var(--text-primary) ${zoomPct}%, var(--border-strong) ${zoomPct}%)`,
            }}
          />
          <div className="flex w-full max-w-[20rem] items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleResetCrop}
              className="flex-1"
            >
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("sessions.room.photo.reset", { defaultValue: "Reset" })}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleCancelPick}
              disabled={busy}
              className="flex-1"
            >
              {t("common.cancel", { defaultValue: "Cancel" })}
            </Button>
            <Button
              type="button"
              variant="accent"
              size="sm"
              onClick={() => void handleUpload()}
              disabled={busy}
              className="flex-1"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} aria-hidden />
              ) : (
                <Upload className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              )}
              {busy
                ? t("sessions.room.photo.uploading", {
                    defaultValue: "Uploading…",
                  })
                : t("sessions.room.photo.upload", {
                    defaultValue: "Upload",
                  })}
            </Button>
          </div>
        </>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="max-w-[20rem] text-center text-[0.75rem] text-[var(--tone-danger-dot)]"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

function CropCanvas({
  image,
  zoom,
  offset,
}: {
  image: LoadedImage;
  zoom: number;
  offset: { x: number; y: number };
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
    const targetSize = Math.round(CROP_PX * dpr);
    if (canvas.width !== targetSize || canvas.height !== targetSize) {
      canvas.width = targetSize;
      canvas.height = targetSize;
    }
    drawCropOnCanvas(ctx, image, zoom, offset, targetSize);
  }, [image, offset, zoom]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: CROP_PX, height: CROP_PX }}
      className="h-full w-full"
    />
  );
}

function drawCropOnCanvas(
  ctx: CanvasRenderingContext2D,
  image: LoadedImage,
  zoom: number,
  offset: { x: number; y: number },
  outputSize: number,
) {
  const { source, intrinsicWidth, intrinsicHeight } = image;
  const shortest = Math.min(intrinsicWidth, intrinsicHeight);
  const visibleSide = shortest / zoom;
  const sx = intrinsicWidth / 2 - visibleSide / 2 + offset.x;
  const sy = intrinsicHeight / 2 - visibleSide / 2 + offset.y;
  ctx.save();
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, outputSize, outputSize);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(source, sx, sy, visibleSide, visibleSide, 0, 0, outputSize, outputSize);
  ctx.restore();
}

async function renderCroppedJpeg(
  image: LoadedImage,
  zoom: number,
  offset: { x: number; y: number },
): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = OUTPUT_PX;
  canvas.height = OUTPUT_PX;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d context unavailable");
  drawCropOnCanvas(ctx, image, zoom, offset, OUTPUT_PX);
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("toBlob produced null"));
          return;
        }
        resolve(blob);
      },
      "image/jpeg",
      OUTPUT_QUALITY,
    );
  });
}
