"use client";

import { motion, useReducedMotion } from "framer-motion";

export type TourSpotlightFrame = {
  top: number;
  left: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
  radius: number;
};

export function getTourSpotlightFrame(rect: {
  top: number;
  left: number;
  width: number;
  height: number;
  radius?: number;
}): TourSpotlightFrame {
  const viewportWidth = typeof window === "undefined" ? 1440 : window.innerWidth;
  const viewportHeight = typeof window === "undefined" ? 900 : window.innerHeight;
  const viewportPadding = viewportWidth < 1024 ? 4 : 4;
  const isTallRail =
    rect.height > viewportHeight * 0.45 && rect.width < viewportWidth * 0.42;
  const effectiveRect = isTallRail
    ? {
        top: rect.top + Math.min(Math.max(rect.height * 0.04, 12), 22),
        left: rect.left,
        width: rect.width,
        height: Math.min(rect.height, Math.max(180, Math.min(300, viewportHeight * 0.32))),
      }
    : rect;
  const padding = Math.min(
    Math.max(
      Math.max(effectiveRect.width, effectiveRect.height) * (viewportWidth < 1024 ? 0.012 : 0.016),
      viewportWidth < 1024 ? 2 : 3,
    ),
    viewportWidth < 1024 ? 4 : 5,
  );
  const expandedWidth = effectiveRect.width + padding * 2;
  const expandedHeight = effectiveRect.height + padding * 2;
  const maxWidth = Math.max(viewportWidth - viewportPadding * 2, 24);
  const maxHeight = Math.max(viewportHeight - viewportPadding * 2, 24);
  const width = Math.min(Math.max(expandedWidth, 24), maxWidth);
  const height = Math.min(Math.max(expandedHeight, 24), maxHeight);
  const rawLeft = effectiveRect.left + effectiveRect.width / 2 - width / 2;
  const rawTop = effectiveRect.top + effectiveRect.height / 2 - height / 2;
  const left = Math.min(
    Math.max(rawLeft, viewportPadding),
    viewportWidth - width - viewportPadding,
  );
  const top = Math.min(
    Math.max(rawTop, viewportPadding),
    viewportHeight - height - viewportPadding,
  );

  return {
    top,
    left,
    width,
    height,
    right: left + width,
    bottom: top + height,
    radius: Math.min(rect.radius ?? 18, Math.min(width, height) / 2),
  };
}

export function TourSpotlight({
  rect,
}: {
  rect: TourSpotlightFrame | null;
}) {
  const reduceMotion = useReducedMotion();

  if (!rect) return null;

  return (
    <motion.div
      className="tour-spotlight"
      aria-hidden="true"
      initial={
        reduceMotion
          ? false
          : {
              opacity: 0,
              scale: 0.985,
            }
      }
      animate={{
        opacity: 1,
        scale: 1,
      }}
      exit={
        reduceMotion
          ? undefined
          : {
              opacity: 0,
              scale: 0.992,
            }
      }
      transition={{
        duration: reduceMotion ? 0 : 0.22,
        ease: [0.22, 1, 0.36, 1],
      }}
      style={{
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
        borderRadius: rect.radius,
      }}
    />
  );
}
