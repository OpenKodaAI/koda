"use client";

import { createPortal } from "react-dom";
import type { CSSProperties, ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import type { TourSpotlightFrame } from "@/components/tour/tour-spotlight";

function getOverlayPaneStyles(rect: TourSpotlightFrame): CSSProperties[] {
  const top = Math.max(rect.top, 0);
  const left = Math.max(rect.left, 0);
  const right = Math.max(rect.right, 0);
  const bottom = Math.max(rect.bottom, 0);
  const height = Math.max(rect.height, 0);

  return [
    { top: 0, left: 0, right: 0, height: top },
    { top: bottom, left: 0, right: 0, bottom: 0 },
    { top, left: 0, width: left, height },
    { top, left: right, right: 0, height },
  ];
}

export function TourOverlay({
  children,
  spotlightRect,
}: {
  children: ReactNode;
  spotlightRect?: TourSpotlightFrame | null;
}) {
  const reduceMotion = useReducedMotion();

  if (typeof document === "undefined") {
    return null;
  }

  const paneStyles = spotlightRect ? getOverlayPaneStyles(spotlightRect) : [];

  return createPortal(
    <motion.div
      className="tour-layer"
      initial={
        reduceMotion
          ? false
          : {
              opacity: 0,
            }
      }
      animate={{
        opacity: 1,
      }}
      transition={{
        duration: reduceMotion ? 0 : 0.24,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      {spotlightRect ? (
        <>
          {paneStyles.map((style, index) => (
            <div
              key={`tour-blur-pane-${index}`}
              className="tour-layer__pane tour-layer__pane--blur"
              aria-hidden="true"
              style={style}
            />
          ))}
          {paneStyles.map((style, index) => (
            <div
              key={`tour-backdrop-pane-${index}`}
              className="tour-layer__pane tour-layer__pane--backdrop"
              aria-hidden="true"
              style={style}
            />
          ))}
        </>
      ) : (
        <>
          <div className="tour-layer__blur" aria-hidden="true" />
          <div className="tour-layer__backdrop" aria-hidden="true" />
        </>
      )}
      {children}
    </motion.div>,
    document.body,
  );
}
