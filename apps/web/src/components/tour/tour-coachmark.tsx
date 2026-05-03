"use client";

import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type Variants,
} from "framer-motion";
import type { CSSProperties, RefObject } from "react";
import { KodaMark } from "@/components/layout/koda-mark";
import { ActionButton } from "@/components/ui/action-button";
import { cn } from "@/lib/utils";
import { TourProgress } from "@/components/tour/tour-progress";

export function TourCoachmark({
  title,
  description,
  current,
  total,
  onBack,
  onContinue,
  onSkip,
  backLabel,
  continueLabel,
  skipLabel,
  showBack,
  showSkip,
  panelRef,
  stepKey,
  stepDirection,
  style,
  welcome = false,
  className,
}: {
  title: string;
  description: string;
  current: number;
  total: number;
  onBack: () => void;
  onContinue: () => void;
  onSkip: () => void;
  backLabel: string;
  continueLabel: string;
  skipLabel: string;
  showBack: boolean;
  showSkip: boolean;
  panelRef: RefObject<HTMLDivElement | null>;
  stepKey: string;
  stepDirection: number;
  style?: CSSProperties;
  welcome?: boolean;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const enterEase = [0.22, 1, 0.36, 1] as const;
  const exitEase = [0.4, 0, 1, 1] as const;

  const sceneVariants: Variants | undefined = reduceMotion
    ? undefined
    : {
        enter: (direction: number) => ({
          opacity: 0,
          x: direction < 0 ? -16 : 16,
          y: 4,
        }),
        center: {
          opacity: 1,
          x: 0,
          y: 0,
          transition: {
            duration: 0.24,
            ease: enterEase,
            staggerChildren: 0.04,
            delayChildren: 0.02,
          },
        },
        exit: (direction: number) => ({
          opacity: 0,
          x: direction < 0 ? 12 : -12,
          y: -4,
          transition: {
            duration: 0.16,
            ease: exitEase,
          },
        }),
      };

  const childVariants: Variants | undefined = reduceMotion
    ? undefined
    : {
        enter: { opacity: 0, y: 6 },
        center: {
          opacity: 1,
          y: 0,
          transition: { duration: 0.2, ease: enterEase },
        },
        exit: {
          opacity: 0,
          y: -4,
          transition: { duration: 0.14, ease: exitEase },
        },
      };

  return (
    <motion.div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      className={cn("tour-coachmark", className)}
      style={style}
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduceMotion ? undefined : { opacity: 0, y: 4 }}
      transition={{
        duration: reduceMotion ? 0 : 0.2,
        ease: enterEase,
      }}
    >
      <AnimatePresence mode="wait" initial={false} custom={stepDirection}>
        <motion.div
          key={stepKey}
          className="tour-coachmark__scene"
          custom={stepDirection}
          variants={sceneVariants}
          initial={reduceMotion ? false : "enter"}
          animate="center"
          exit={reduceMotion ? undefined : "exit"}
        >
          {welcome ? (
            <motion.div
              className="tour-coachmark__brand"
              variants={childVariants}
              aria-hidden="true"
            >
              <KodaMark className="tour-coachmark__brand-mark" />
              <span className="tour-coachmark__brand-name">Koda</span>
            </motion.div>
          ) : null}
          <motion.div className="tour-coachmark__header" variants={childVariants}>
            <TourProgress current={current} total={total} />
          </motion.div>
          <motion.div className="tour-coachmark__body" variants={childVariants}>
            <h2 className="tour-coachmark__title">{title}</h2>
            <p className="tour-coachmark__description">{description}</p>
          </motion.div>
          <motion.div className="tour-coachmark__actions" variants={childVariants}>
            {showBack ? (
              <ActionButton type="button" variant="secondary" onClick={onBack}>
                {backLabel}
              </ActionButton>
            ) : (
              <span className="tour-coachmark__spacer" aria-hidden="true" />
            )}
            <div className="tour-coachmark__actions-trailing">
              {showSkip ? (
                <ActionButton type="button" variant="quiet" onClick={onSkip}>
                  {skipLabel}
                </ActionButton>
              ) : null}
              <ActionButton type="button" variant="primary" onClick={onContinue}>
                {continueLabel}
              </ActionButton>
            </div>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
}
