"use client";

import Image from "next/image";
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
  mobile,
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
  mobile?: boolean;
  welcome?: boolean;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const enterEase = [0.22, 1, 0.36, 1] as const;
  const exitEase = [0.4, 0, 1, 1] as const;
  const welcomeDialogStyle: CSSProperties | undefined = welcome
    ? {
        ...style,
        overflow: mobile ? style?.overflow : "hidden",
        minHeight: mobile ? style?.minHeight : "22.4rem",
      }
    : style;

  const welcomeShellStyle: CSSProperties | undefined = welcome
    ? mobile
      ? undefined
      : {
          justifyContent: "center",
          gap: "0.7rem",
          padding:
            "0.9rem clamp(21.75rem, 30vw, 25rem) 0.9rem clamp(1rem, 2vw, 1.35rem)",
        }
    : undefined;

  const welcomeStageStyle: CSSProperties | undefined = welcome
    ? mobile
      ? undefined
      : {
          position: "absolute",
          top: "0",
          right: "0",
          width: "34rem",
          bottom: "0",
          padding: 0,
          overflow: "visible",
          pointerEvents: "none",
          zIndex: 0,
          borderTopRightRadius: "1rem",
          borderBottomRightRadius: "1rem",
        }
    : undefined;

  const welcomeImageStyle: CSSProperties | undefined = welcome
    ? mobile
      ? undefined
      : {
          position: "absolute",
          top: "3rem",
          right: "-5.9rem",
          width: "auto",
          height: "calc(100% + 9.8rem)",
          maxWidth: "none",
          transform: "rotate(23deg)",
          transformOrigin: "top right",
          filter: "drop-shadow(0 24px 38px rgba(0, 0, 0, 0.48))",
        }
    : undefined;

  const sceneVariants: Variants | undefined = reduceMotion
    ? undefined
    : {
        enter: (direction: number) => ({
          opacity: 0,
          x: direction < 0 ? -24 : 24,
          y: welcome ? 10 : 6,
          scale: welcome ? 0.985 : 0.992,
          filter: "blur(12px)",
        }),
        center: {
          opacity: 1,
          x: 0,
          y: 0,
          scale: 1,
          filter: "blur(0px)",
          transition: {
            duration: 0.34,
            ease: enterEase,
            staggerChildren: 0.055,
            delayChildren: 0.04,
          },
        },
        exit: (direction: number) => ({
          opacity: 0,
          x: direction < 0 ? 20 : -20,
          y: welcome ? -6 : -4,
          scale: 0.992,
          filter: "blur(10px)",
          transition: {
            duration: 0.2,
            ease: exitEase,
          },
        }),
      };

  const childVariants: Variants | undefined = reduceMotion
    ? undefined
    : {
        enter: {
          opacity: 0,
          y: 12,
          filter: "blur(10px)",
        },
        center: {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          transition: {
            duration: 0.28,
            ease: enterEase,
          },
        },
        exit: {
          opacity: 0,
          y: -8,
          filter: "blur(8px)",
          transition: {
            duration: 0.16,
            ease: exitEase,
          },
        },
      };

  const illustrationVariants: Variants | undefined = reduceMotion
    ? undefined
    : {
        enter: {
          opacity: 0,
          x: 26,
          y: 14,
          scale: 0.97,
          rotate: 3,
          filter: "blur(12px)",
        },
        center: {
          opacity: 1,
          x: 0,
          y: 0,
          scale: 1,
          rotate: 0,
          filter: "blur(0px)",
          transition: {
            duration: 0.42,
            ease: enterEase,
            delay: 0.06,
          },
        },
        exit: {
          opacity: 0,
          x: -14,
          y: -10,
          scale: 0.985,
          filter: "blur(10px)",
          transition: {
            duration: 0.18,
            ease: exitEase,
          },
        },
      };

  if (welcome) {
    return (
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        className={cn(
          "tour-coachmark tour-coachmark--welcome",
          mobile && "tour-coachmark--mobile",
          className,
        )}
        style={welcomeDialogStyle}
        initial={
          reduceMotion
            ? false
            : {
                opacity: 0,
                filter: "blur(14px)",
              }
        }
        animate={{
          opacity: 1,
          filter: "blur(0px)",
        }}
        exit={
          reduceMotion
            ? undefined
            : {
                opacity: 0,
                filter: "blur(12px)",
              }
        }
        transition={{
          duration: reduceMotion ? 0 : 0.36,
          ease: enterEase,
        }}
      >
        <AnimatePresence mode="wait" initial={false} custom={stepDirection}>
          <motion.div
            key={stepKey}
            className="tour-coachmark__scene tour-coachmark__scene--welcome"
            custom={stepDirection}
            variants={sceneVariants}
            initial={reduceMotion ? false : "enter"}
            animate="center"
            exit={reduceMotion ? undefined : "exit"}
          >
            <motion.div
              className="tour-coachmark__welcome-stage"
              aria-hidden="true"
              style={welcomeStageStyle}
              variants={illustrationVariants}
            >
              <Image
                src="/koda_illustration.png"
                alt=""
                aria-hidden="true"
                width={1584}
                height={2336}
                priority
                unoptimized
                sizes="(max-width: 768px) 180px, 240px"
                className="tour-coachmark__welcome-illustration"
                style={welcomeImageStyle}
              />
            </motion.div>

            <div
              className="tour-coachmark__welcome-shell"
              style={welcomeShellStyle}
            >
              <motion.div
                className="tour-coachmark__welcome-brand"
                variants={childVariants}
              >
                <span className="tour-coachmark__welcome-brand-mark">
                  <KodaMark className="tour-coachmark__welcome-brand-logo" />
                </span>
                <span className="tour-coachmark__welcome-brand-titleword">
                  Koda
                </span>
              </motion.div>

              <motion.div
                className="tour-coachmark__header tour-coachmark__header--welcome"
                variants={childVariants}
              >
                <TourProgress current={current} total={total} />
              </motion.div>

              <motion.div
                className="tour-coachmark__body tour-coachmark__body--welcome"
                variants={childVariants}
              >
                <h2 className="tour-coachmark__title tour-coachmark__title--welcome">
                  {title}
                </h2>
                <p className="tour-coachmark__description tour-coachmark__description--welcome">
                  {description}
                </p>
              </motion.div>

              <motion.div
                className="tour-coachmark__actions tour-coachmark__actions--welcome"
                variants={childVariants}
              >
                {showSkip ? (
                  <ActionButton
                    type="button"
                    variant="quiet"
                    onClick={onSkip}
                    className="tour-coachmark__welcome-button"
                  >
                    {skipLabel}
                  </ActionButton>
                ) : null}
                <ActionButton
                  type="button"
                  variant="primary"
                  onClick={onContinue}
                  className="tour-coachmark__welcome-button tour-coachmark__welcome-button--primary"
                >
                  {continueLabel}
                </ActionButton>
              </motion.div>
            </div>
          </motion.div>
        </AnimatePresence>
      </motion.div>
    );
  }

  return (
    <motion.div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      className={cn(
        "tour-coachmark",
        mobile && "tour-coachmark--mobile",
        className,
      )}
      style={style}
      initial={
        reduceMotion
          ? false
          : {
              opacity: 0,
              filter: "blur(12px)",
            }
      }
      animate={{
        opacity: 1,
        filter: "blur(0px)",
      }}
      exit={
        reduceMotion
          ? undefined
          : {
              opacity: 0,
              filter: "blur(10px)",
            }
      }
      transition={{
        duration: reduceMotion ? 0 : 0.28,
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
