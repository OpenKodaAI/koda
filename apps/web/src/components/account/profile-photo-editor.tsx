"use client";

import {
  type ChangeEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Camera, Check, ImageOff, LoaderCircle, RotateCcw, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { OperatorAvatar } from "@/components/ui/avatar-picker";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

const IDLE_PX = 96;
const CROP_PX = 192;
const OUTPUT_PX = 512;
const OUTPUT_QUALITY = 0.88;
const MAX_IMAGE_BYTES = 12 * 1024 * 1024;
type UploadStage = "idle" | "preparing" | "uploading";

interface LoadedImage {
  source: HTMLImageElement;
  intrinsicWidth: number;
  intrinsicHeight: number;
  objectUrl: string;
}

export interface ProfilePhotoEditorProps {
  currentPhotoUrl?: string | null;
  displayName: string;
  fallbackAvatarId?: string | null;
  onUpload: (blob: Blob) => Promise<void>;
  onRemove: () => Promise<void>;
  className?: string;
}

function initialsForName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.charAt(0) ?? "";
  const second = parts.length > 1 ? (parts[1]?.charAt(0) ?? "") : "";
  return `${first}${second}`.toUpperCase() || "?";
}

function waitForNextPaint() {
  if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
    return new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  return new Promise<void>((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(fallbackId);
      resolve();
    };
    const fallbackId = window.setTimeout(finish, 120);
    window.requestAnimationFrame(() => window.setTimeout(finish, 0));
  });
}

export function ProfilePhotoEditor({
  currentPhotoUrl,
  displayName,
  fallbackAvatarId,
  onUpload,
  onRemove,
  className,
}: ProfilePhotoEditorProps) {
  const { t } = useAppI18n();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [picked, setPicked] = useState<LoadedImage | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [uploadStage, setUploadStage] = useState<UploadStage>("idle");
  const [removing, setRemoving] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initials = useMemo(() => initialsForName(displayName), [displayName]);
  const minZoom = useMemo(() => {
    if (!picked) return 1;
    const longest = Math.max(picked.intrinsicWidth, picked.intrinsicHeight);
    const shortest = Math.min(picked.intrinsicWidth, picked.intrinsicHeight);
    return longest / shortest;
  }, [picked]);
  const maxZoom = minZoom * 4;
  const zoomPct = maxZoom > minZoom ? ((zoom - minZoom) / (maxZoom - minZoom)) * 100 : 0;

  const releasePicked = useCallback((next: LoadedImage | null) => {
    setPicked((current) => {
      if (current?.objectUrl && current.objectUrl !== next?.objectUrl) {
        URL.revokeObjectURL(current.objectUrl);
      }
      return next;
    });
  }, []);

  useEffect(() => {
    return () => {
      if (picked?.objectUrl) {
        URL.revokeObjectURL(picked.objectUrl);
      }
    };
  }, [picked?.objectUrl]);

  useEffect(() => {
    if (!picked) return;
    setZoom(minZoom);
    setOffset({ x: 0, y: 0 });
  }, [minZoom, picked]);

  useEffect(() => {
    setImgError(false);
  }, [currentPhotoUrl]);

  const clampOffset = useCallback((next: { x: number; y: number }, zoomValue: number, image: LoadedImage) => {
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
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (!file.type.startsWith("image/")) {
        setError(t("account.profile.photo.invalid_type", undefined));
        return;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        setError(t("account.profile.photo.too_large", undefined));
        return;
      }

      const objectUrl = URL.createObjectURL(file);
      try {
        const image = new Image();
        image.decoding = "async";
        image.src = objectUrl;
        await image.decode().catch(() => {
          return new Promise<void>((resolve, reject) => {
            image.onload = () => resolve();
            image.onerror = () => reject(new Error("decode failed"));
          });
        });
        releasePicked({
          source: image,
          intrinsicWidth: image.naturalWidth || image.width,
          intrinsicHeight: image.naturalHeight || image.height,
          objectUrl,
        });
      } catch {
        URL.revokeObjectURL(objectUrl);
        setError(t("account.profile.photo.decode_failed", undefined));
      }
    },
    [releasePicked, t],
  );

  const handleFileChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) void handleFile(file);
      event.target.value = "";
    },
    [handleFile],
  );

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

  const handlePointerUp = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
  }, []);

  const handleZoomChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const next = Number.parseFloat(event.target.value);
      if (!Number.isFinite(next) || !picked) return;
      const clamped = Math.max(minZoom, Math.min(next, maxZoom));
      setZoom(clamped);
      setOffset((current) => clampOffset(current, clamped, picked));
    },
    [clampOffset, maxZoom, minZoom, picked],
  );

  const handleResetCrop = useCallback(() => {
    setZoom(minZoom);
    setOffset({ x: 0, y: 0 });
  }, [minZoom]);

  const handleUpload = useCallback(async () => {
    if (!picked || uploadStage !== "idle") return;
    setUploadStage("preparing");
    setError(null);
    try {
      await waitForNextPaint();
      const blob = await renderCroppedJpeg(picked, zoom, offset);
      setUploadStage("uploading");
      await waitForNextPaint();
      await onUpload(blob);
      releasePicked(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("account.profile.photo.upload_failed", undefined));
    } finally {
      setUploadStage("idle");
    }
  }, [offset, onUpload, picked, releasePicked, t, uploadStage, zoom]);

  const handleRemove = useCallback(
    async (event?: ReactMouseEvent) => {
      event?.stopPropagation();
      if (removing) return;
      setRemoving(true);
      setError(null);
      try {
        await onRemove();
      } catch (err) {
        setError(err instanceof Error ? err.message : t("account.profile.photo.remove_failed", undefined));
      } finally {
        setRemoving(false);
      }
    },
    [onRemove, removing, t],
  );

  const isCropping = picked !== null;
  const isUploading = uploadStage !== "idle";
  const isBusy = isUploading || removing;
  const showImage = !isCropping && Boolean(currentPhotoUrl) && !imgError;
  const sizePx = isCropping ? CROP_PX : IDLE_PX;
  const uploadStatus = uploadStage === "preparing"
    ? t("account.profile.photo.preparing", undefined)
    : t("account.profile.photo.saving", undefined);

  return (
    <div className={cn("flex min-w-0 flex-col items-center gap-3", className)}>
      <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} className="hidden" />

      <div
        className="relative"
        style={{
          width: sizePx,
          height: sizePx,
          transition: "width 200ms var(--ease-out-quart), height 200ms var(--ease-out-quart)",
        }}
      >
        <button
          type="button"
          onClick={isCropping ? undefined : () => fileInputRef.current?.click()}
          onPointerDown={isCropping ? handlePointerDown : undefined}
          onPointerMove={isCropping ? handlePointerMove : undefined}
          onPointerUp={isCropping ? handlePointerUp : undefined}
          onPointerCancel={isCropping ? handlePointerUp : undefined}
          disabled={isBusy}
          aria-label={
            isCropping
              ? t("account.profile.photo.adjust", undefined)
              : t("account.profile.photo.choose", undefined)
          }
          className={cn(
            "group relative flex h-full w-full items-center justify-center overflow-hidden rounded-full border-0 bg-[var(--panel-soft)] p-0 outline-none ring-1 ring-[color:var(--border-subtle)]",
            "transition-[background-color,box-shadow] duration-[160ms] ease-[var(--ease-out-quart)]",
            !isCropping && !isBusy && "cursor-pointer hover:bg-[var(--panel)] hover:ring-[color:var(--border-strong)] focus-visible:ring-2 focus-visible:ring-[color:var(--accent)]",
            isCropping && "cursor-grab select-none touch-none active:cursor-grabbing",
            isBusy && "cursor-wait",
          )}
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
            <span className="flex h-full w-full items-center justify-center font-mono text-[1.55rem] font-medium text-[var(--text-secondary)]">
              {imgError ? (
                <ImageOff className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
              ) : fallbackAvatarId ? (
                <OperatorAvatar avatarId={fallbackAvatarId} size={IDLE_PX} className="h-full w-full" />
              ) : (
                initials
              )}
            </span>
          )}

          {!isCropping ? (
            <span
              className={cn(
                "pointer-events-none absolute inset-0 flex items-center justify-center bg-black/0 text-white/0 transition-[background-color,color] duration-[160ms] ease-[var(--ease-out-quart)]",
                !isBusy && "group-hover:bg-black/38 group-hover:text-white group-focus-visible:bg-black/38 group-focus-visible:text-white",
              )}
            >
              <Camera className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </span>
          ) : null}

          {isBusy ? (
            <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/62 text-white backdrop-blur-[1px]">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-black/35 ring-1 ring-white/25">
                <LoaderCircle className="h-5 w-5 animate-spin" strokeWidth={2} aria-hidden="true" />
              </span>
            </span>
          ) : null}
        </button>

        {!isCropping && currentPhotoUrl ? (
          <button
            type="button"
            onClick={(event) => void handleRemove(event)}
            disabled={isBusy}
            aria-label={t("account.profile.photo.remove", undefined)}
            className="flex h-6 w-6 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--panel-strong)] text-[var(--text-tertiary)] shadow-[var(--shadow-xs)] transition-[background-color,border-color,color] duration-[160ms] hover:border-[var(--tone-danger-border)] hover:bg-[var(--tone-danger-bg)] hover:text-[var(--tone-danger-dot)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-wait disabled:opacity-80"
            style={{ position: "absolute", top: -4, right: -4, transform: "translateZ(0)" }}
          >
            {removing ? (
              <LoaderCircle className="h-3 w-3 animate-spin" strokeWidth={2} aria-hidden="true" />
            ) : (
              <Trash2 className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
            )}
          </button>
        ) : null}
      </div>

      {isCropping ? (
        <div className="flex w-full max-w-[12rem] flex-col items-stretch gap-3">
          <input
            type="range"
            min={minZoom}
            max={maxZoom}
            step={0.01}
            value={zoom}
            onChange={handleZoomChange}
            disabled={isUploading}
            aria-label={t("account.profile.photo.zoom", undefined)}
            className="ui-slider w-full disabled:cursor-wait disabled:opacity-70"
            style={{
              height: 8,
              background: `linear-gradient(to right, var(--text-primary) ${zoomPct}%, var(--border-strong) ${zoomPct}%)`,
            }}
          />
          <div className="grid w-full grid-cols-2 gap-2">
            <Button type="button" variant="outline" size="sm" onClick={handleResetCrop} disabled={isUploading} className="min-w-0 px-2">
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              <span>{t("common.reset", undefined)}</span>
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => releasePicked(null)}
              disabled={isUploading}
              className="min-w-0 px-2"
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              <span>{t("common.cancel", undefined)}</span>
            </Button>
            <Button
              type="button"
              variant="accent"
              size="sm"
              onClick={() => void handleUpload()}
              disabled={isUploading}
              aria-label={isUploading ? uploadStatus : t("common.save", undefined)}
              aria-busy={isUploading}
              className={cn("col-span-2 min-w-0", isUploading && "ring-1 ring-[var(--accent)]")}
            >
              {isUploading ? (
                <LoaderCircle className="h-3.5 w-3.5 animate-spin" strokeWidth={2} aria-hidden="true" />
              ) : (
                <Check className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              <span>{t("common.save", undefined)}</span>
            </Button>
          </div>
          {isUploading ? (
            <span className="sr-only" role="status">
              {uploadStatus}
            </span>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="m-0 max-w-[20rem] text-center text-[0.75rem] leading-5 text-[var(--tone-danger-dot)]">
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
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
    const targetSize = Math.round(CROP_PX * dpr);
    if (canvas.width !== targetSize || canvas.height !== targetSize) {
      canvas.width = targetSize;
      canvas.height = targetSize;
    }
    drawCropOnCanvas(ctx, image, zoom, offset, targetSize);
  }, [image, offset, zoom]);

  return <canvas ref={canvasRef} style={{ width: CROP_PX, height: CROP_PX }} className="h-full w-full" />;
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

async function renderCroppedJpeg(image: LoadedImage, zoom: number, offset: { x: number; y: number }): Promise<Blob> {
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
