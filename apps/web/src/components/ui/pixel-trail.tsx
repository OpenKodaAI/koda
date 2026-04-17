"use client";

import React, { useCallback, useMemo, useRef, useState } from "react";
import { motion, useAnimationControls } from "framer-motion";
import { useDimensions } from "@/hooks/use-debounced-dimensions";
import { cn } from "@/lib/utils";

let pixelTrailCounter = 0;
function createTrailId(): string {
  if (typeof globalThis !== "undefined" && typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  pixelTrailCounter += 1;
  return `pixel-trail-${pixelTrailCounter}-${Date.now().toString(36)}`;
}

interface PixelTrailProps {
  pixelSize?: number;
  fadeDuration?: number;
  delay?: number;
  className?: string;
  pixelClassName?: string;
}

export function PixelTrail({
  pixelSize = 20,
  fadeDuration = 500,
  delay = 0,
  className,
  pixelClassName,
}: PixelTrailProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dimensions = useDimensions(containerRef);
  const [trailPrefix] = useState(() => createTrailId());
  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = Math.floor((event.clientX - rect.left) / pixelSize);
      const y = Math.floor((event.clientY - rect.top) / pixelSize);

      const pixelElement = document.getElementById(
        `${trailPrefix}-pixel-${x}-${y}`,
      );
      if (pixelElement) {
        const animatePixel = (pixelElement as HTMLElement & { __animatePixel?: () => void })
          .__animatePixel;
        if (animatePixel) animatePixel();
      }
    },
    [pixelSize, trailPrefix],
  );

  const columns = useMemo(
    () => Math.ceil(dimensions.width / pixelSize),
    [dimensions.width, pixelSize],
  );
  const rows = useMemo(
    () => Math.ceil(dimensions.height / pixelSize),
    [dimensions.height, pixelSize],
  );

  return (
    <div
      ref={containerRef}
      className={cn("absolute inset-0 h-full w-full pointer-events-auto", className)}
      onMouseMove={handleMouseMove}
      aria-hidden="true"
    >
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <PixelDot
              key={`${colIndex}-${rowIndex}`}
              id={`${trailPrefix}-pixel-${colIndex}-${rowIndex}`}
              size={pixelSize}
              fadeDuration={fadeDuration}
              delay={delay}
              className={pixelClassName}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

interface PixelDotProps {
  id: string;
  size: number;
  fadeDuration: number;
  delay: number;
  className?: string;
}

const PixelDot = React.memo(function PixelDot({
  id,
  size,
  fadeDuration,
  delay,
  className,
}: PixelDotProps) {
  const controls = useAnimationControls();

  const animatePixel = useCallback(() => {
    controls.start({
      opacity: [1, 0],
      transition: { duration: fadeDuration / 1000, delay: delay / 1000 },
    });
  }, [controls, fadeDuration, delay]);

  const ref = useCallback(
    (node: HTMLDivElement | null) => {
      if (node) {
        (node as HTMLElement & { __animatePixel?: () => void }).__animatePixel = animatePixel;
      }
    },
    [animatePixel],
  );

  return (
    <motion.div
      id={id}
      ref={ref}
      className={cn("pointer-events-none", className)}
      style={{ width: `${size}px`, height: `${size}px` }}
      initial={{ opacity: 0 }}
      animate={controls}
      exit={{ opacity: 0 }}
    />
  );
});
