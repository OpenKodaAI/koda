/* Shared animation constants for the control-plane editor */

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

export const SPRING_SWITCH = {
  type: "spring" as const,
  stiffness: 500,
  damping: 30,
};

export const DURATION_DEFAULT = 0.2;
export const DURATION_EXPAND = 0.25;

export const COLLAPSE_TRANSITION = {
  duration: DURATION_EXPAND,
  ease: EASE_OUT,
};

export const FADE_TRANSITION = {
  duration: DURATION_DEFAULT,
  ease: EASE_OUT,
};
