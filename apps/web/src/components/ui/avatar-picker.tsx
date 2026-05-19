"use client";

import { useId, useMemo, useSyncExternalStore } from "react";
import { Check } from "lucide-react";
import { safeLocalStorageGet, safeLocalStorageSet } from "@/lib/browser-storage";
import { cn } from "@/lib/utils";

export interface AvatarOption {
  id: string;
  label: string;
  alt: string;
  colors: {
    base: string;
    accent: string;
    ink: string;
  };
  face: {
    eyes: "round" | "soft" | "sleepy" | "wink" | "glasses";
    mouth: "smile" | "grin" | "smirk" | "calm" | "oh";
    detail: "freckles" | "brows" | "cheeks" | "spark" | "mole" | "none";
    gaze: [number, number];
    bob: string;
    glance: string;
    blink: string;
    delay: string;
  };
}

export const avatarOptions: AvatarOption[] = [
  {
    id: "ember",
    label: "Ember",
    alt: "Warm animated avatar",
    colors: { base: "#D97757", accent: "#F4B27A", ink: "#24110B" },
    face: { eyes: "round", mouth: "grin", detail: "freckles", gaze: [0.45, -0.1], bob: "4.8s", glance: "6.4s", blink: "5.2s", delay: "0.2s" },
  },
  {
    id: "harbor",
    label: "Harbor",
    alt: "Teal animated avatar",
    colors: { base: "#2A9D8F", accent: "#8EDAD0", ink: "#061C1A" },
    face: { eyes: "soft", mouth: "smile", detail: "cheeks", gaze: [-0.5, 0.1], bob: "5.4s", glance: "7.1s", blink: "4.9s", delay: "1.1s" },
  },
  {
    id: "graphite",
    label: "Graphite",
    alt: "Graphite animated avatar",
    colors: { base: "#2A2A2A", accent: "#B8B8B8", ink: "#F5F5F5" },
    face: { eyes: "sleepy", mouth: "calm", detail: "brows", gaze: [0.3, 0.2], bob: "6.2s", glance: "8.2s", blink: "6.6s", delay: "0.7s" },
  },
  {
    id: "sage",
    label: "Sage",
    alt: "Sage animated avatar",
    colors: { base: "#8FAE7E", accent: "#DCE9C8", ink: "#182114" },
    face: { eyes: "round", mouth: "calm", detail: "mole", gaze: [-0.3, -0.15], bob: "5.8s", glance: "7.8s", blink: "5.8s", delay: "1.7s" },
  },
  {
    id: "cobalt",
    label: "Cobalt",
    alt: "Cobalt animated avatar",
    colors: { base: "#4A6FA5", accent: "#BFD2F2", ink: "#081424" },
    face: { eyes: "glasses", mouth: "smirk", detail: "brows", gaze: [0.55, 0], bob: "5.1s", glance: "6.8s", blink: "5.6s", delay: "0.5s" },
  },
  {
    id: "rosewood",
    label: "Rosewood",
    alt: "Rosewood animated avatar",
    colors: { base: "#9C496A", accent: "#F0B7C8", ink: "#260B15" },
    face: { eyes: "wink", mouth: "smirk", detail: "cheeks", gaze: [0.35, -0.05], bob: "4.9s", glance: "6.1s", blink: "4.7s", delay: "1.3s" },
  },
  {
    id: "ochre",
    label: "Ochre",
    alt: "Ochre animated avatar",
    colors: { base: "#B98535", accent: "#F0D08A", ink: "#221508" },
    face: { eyes: "round", mouth: "oh", detail: "spark", gaze: [-0.45, -0.2], bob: "4.7s", glance: "5.9s", blink: "4.6s", delay: "0.9s" },
  },
  {
    id: "violet",
    label: "Violet",
    alt: "Violet animated avatar",
    colors: { base: "#6E5BA8", accent: "#C9BDF1", ink: "#160E2D" },
    face: { eyes: "soft", mouth: "grin", detail: "freckles", gaze: [0.2, 0.25], bob: "5.3s", glance: "7.4s", blink: "5.1s", delay: "1.9s" },
  },
  {
    id: "slate",
    label: "Slate",
    alt: "Slate animated avatar",
    colors: { base: "#64748B", accent: "#D1DAE6", ink: "#0F172A" },
    face: { eyes: "sleepy", mouth: "smile", detail: "none", gaze: [-0.25, 0.1], bob: "6.6s", glance: "8.6s", blink: "6.9s", delay: "1.4s" },
  },
  {
    id: "mint",
    label: "Mint",
    alt: "Mint animated avatar",
    colors: { base: "#5AA88F", accent: "#C9F0DF", ink: "#09241C" },
    face: { eyes: "round", mouth: "smile", detail: "spark", gaze: [0.4, -0.25], bob: "4.6s", glance: "6.2s", blink: "4.8s", delay: "0.1s" },
  },
];

export interface AvatarPickerProps {
  value?: string;
  onChange?: (avatarId: string) => void;
  displayName?: string;
  subtitle?: string;
  className?: string;
  showPreview?: boolean;
}

export const OPERATOR_AVATAR_STORAGE_KEY = "koda.operator.avatar.v1";
export const OPERATOR_AVATAR_CHANGED_EVENT = "koda:operator-avatar-changed";

export function getAvatarOption(avatarId: string | null | undefined) {
  return avatarOptions.find((avatar) => avatar.id === avatarId) ?? avatarOptions[0];
}

export function readStoredOperatorAvatar() {
  if (typeof window === "undefined") return avatarOptions[0].id;
  return getAvatarOption(safeLocalStorageGet(OPERATOR_AVATAR_STORAGE_KEY)).id;
}

function getServerOperatorAvatarSnapshot() {
  return avatarOptions[0].id;
}

function subscribeToStoredOperatorAvatar(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => {};

  window.addEventListener(OPERATOR_AVATAR_CHANGED_EVENT, onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    window.removeEventListener(OPERATOR_AVATAR_CHANGED_EVENT, onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

export function writeStoredOperatorAvatar(avatarId: string) {
  if (typeof window === "undefined") return getAvatarOption(avatarId).id;
  const normalized = getAvatarOption(avatarId).id;
  safeLocalStorageSet(OPERATOR_AVATAR_STORAGE_KEY, normalized);
  window.dispatchEvent(new CustomEvent(OPERATOR_AVATAR_CHANGED_EVENT, { detail: { avatarId: normalized } }));
  return normalized;
}

export function useStoredOperatorAvatar() {
  return useSyncExternalStore(
    subscribeToStoredOperatorAvatar,
    readStoredOperatorAvatar,
    getServerOperatorAvatarSnapshot,
  );
}

function avatarMotionStyles(scope: string, face: AvatarOption["face"]) {
  const [gazeX, gazeY] = face.gaze;
  return `
    .${scope}-face {
      animation: ${scope}-bob ${face.bob} ease-in-out infinite;
      transform-box: fill-box;
      transform-origin: center;
    }
    .${scope}-accent {
      animation: ${scope}-float ${face.bob} ease-in-out infinite;
      transform-box: fill-box;
      transform-origin: center;
    }
    .${scope}-pupil {
      animation: ${scope}-look ${face.glance} ease-in-out infinite;
      animation-delay: ${face.delay};
      transform-box: fill-box;
      transform-origin: center;
    }
    .${scope}-blink {
      animation: ${scope}-blink ${face.blink} ease-in-out infinite;
      animation-delay: ${face.delay};
      transform-box: fill-box;
      transform-origin: center;
    }
    .${scope}-spark {
      animation: ${scope}-spark 3.8s ease-in-out infinite;
      animation-delay: ${face.delay};
      transform-box: fill-box;
      transform-origin: center;
    }
    @keyframes ${scope}-bob {
      0%, 100% { transform: translateY(0) rotate(0deg); }
      45% { transform: translateY(-0.45px) rotate(0.65deg); }
      70% { transform: translateY(0.18px) rotate(-0.35deg); }
    }
    @keyframes ${scope}-float {
      0%, 100% { transform: translate(0, 0); }
      50% { transform: translate(0.2px, -0.3px); }
    }
    @keyframes ${scope}-look {
      0%, 42%, 100% { transform: translate(0, 0); }
      50%, 62% { transform: translate(${gazeX}px, ${gazeY}px); }
      74%, 82% { transform: translate(${-gazeX * 0.55}px, ${-gazeY * 0.35}px); }
    }
    @keyframes ${scope}-blink {
      0%, 88%, 100% { transform: scaleY(1); }
      91%, 94% { transform: scaleY(0.12); }
    }
    @keyframes ${scope}-spark {
      0%, 72%, 100% { opacity: 0.45; transform: scale(0.9) rotate(0deg); }
      80% { opacity: 0.95; transform: scale(1.1) rotate(12deg); }
    }
    @media (prefers-reduced-motion: reduce) {
      .${scope}-face,
      .${scope}-accent,
      .${scope}-pupil,
      .${scope}-blink,
      .${scope}-spark {
        animation: none !important;
      }
    }
  `;
}

function renderEye({
  avatar,
  scope,
  cx,
  cy,
  side,
}: {
  avatar: AvatarOption;
  scope: string;
  cx: number;
  cy: number;
  side: "left" | "right";
}) {
  const { colors, face } = avatar;
  const eyeFill = "#fff";
  const eyeOpacity = colors.ink === "#F5F5F5" ? 0.82 : 0.86;

  if (face.eyes === "sleepy") {
    return (
      <g key={side}>
        <path
          d={`M${cx - 2.45} ${cy + 0.25} Q${cx} ${cy + 1.35} ${cx + 2.45} ${cy + 0.25}`}
          stroke={colors.ink}
          strokeWidth="1.35"
          strokeLinecap="round"
          fill="none"
        />
        <circle className={`${scope}-pupil`} cx={cx + 0.55} cy={cy + 0.52} r="0.5" fill={colors.ink} opacity="0.7" />
      </g>
    );
  }

  if (face.eyes === "wink" && side === "left") {
    return (
      <path
        key={side}
        d={`M${cx - 2.35} ${cy + 0.1} Q${cx} ${cy + 1.15} ${cx + 2.35} ${cy + 0.1}`}
        stroke={colors.ink}
        strokeWidth="1.35"
        strokeLinecap="round"
        fill="none"
      />
    );
  }

  if (face.eyes === "glasses") {
    return (
      <g key={side}>
        <circle cx={cx} cy={cy} r="3.05" fill={eyeFill} opacity="0.2" />
        <circle cx={cx} cy={cy} r="3.05" stroke={colors.ink} strokeWidth="1.15" fill="none" opacity="0.9" />
        <circle className={`${scope}-pupil`} cx={cx} cy={cy + 0.05} r="0.85" fill={colors.ink} />
        <circle cx={cx - 0.85} cy={cy - 0.85} r="0.55" fill={eyeFill} opacity="0.55" />
      </g>
    );
  }

  const soft = face.eyes === "soft";
  return (
    <g key={side} className={`${scope}-blink`}>
      <ellipse cx={cx} cy={cy} rx={soft ? 2.65 : 2.25} ry={soft ? 2.15 : 2.7} fill={eyeFill} opacity={eyeOpacity} />
      <circle className={`${scope}-pupil`} cx={cx} cy={cy + 0.1} r={soft ? 0.92 : 1.02} fill={colors.ink} />
      <circle cx={cx - 0.65} cy={cy - 0.75} r="0.45" fill={eyeFill} opacity="0.75" />
    </g>
  );
}

function renderEyes(avatar: AvatarOption, scope: string) {
  const { colors, face } = avatar;
  return (
    <g>
      {face.eyes === "glasses" ? (
        <path d="M15.05 14.5 C16 13.95 20 13.95 20.95 14.5" stroke={colors.ink} strokeWidth="0.9" strokeLinecap="round" />
      ) : null}
      {renderEye({ avatar, scope, cx: 12.1, cy: 14.9, side: "left" })}
      {renderEye({ avatar, scope, cx: 23.9, cy: 14.9, side: "right" })}
    </g>
  );
}

function renderMouth(avatar: AvatarOption) {
  const { colors, face } = avatar;
  if (face.mouth === "grin") {
    return (
      <g>
        <path d="M13.5 21.05 Q18 25.2 22.5 21.05 Q21.2 24.45 18 24.55 Q14.8 24.45 13.5 21.05Z" fill={colors.ink} opacity="0.92" />
        <path d="M15.5 22.35 Q18 23.25 20.55 22.35" stroke="#fff" strokeWidth="0.65" strokeLinecap="round" opacity="0.65" />
      </g>
    );
  }
  if (face.mouth === "smirk") {
    return <path d="M14.2 22.05 C16.1 23.55 19.75 23.35 21.85 21.4" stroke={colors.ink} strokeWidth="1.45" strokeLinecap="round" fill="none" />;
  }
  if (face.mouth === "calm") {
    return <path d="M15 22.45 H21" stroke={colors.ink} strokeWidth="1.45" strokeLinecap="round" fill="none" opacity="0.85" />;
  }
  if (face.mouth === "oh") {
    return <ellipse cx="18" cy="22.35" rx="1.55" ry="2" fill={colors.ink} opacity="0.9" />;
  }
  return <path d="M14.2 21.85 Q18 24.15 21.8 21.85" stroke={colors.ink} strokeWidth="1.45" strokeLinecap="round" fill="none" />;
}

function renderDetails(avatar: AvatarOption, scope: string) {
  const { colors, face } = avatar;
  if (face.detail === "freckles") {
    return (
      <g fill={colors.ink} opacity="0.42">
        <circle cx="9.2" cy="19.4" r="0.45" />
        <circle cx="11" cy="20.2" r="0.36" />
        <circle cx="25" cy="19.35" r="0.45" />
        <circle cx="26.8" cy="20.15" r="0.36" />
      </g>
    );
  }
  if (face.detail === "brows") {
    return (
      <g stroke={colors.ink} strokeWidth="1.1" strokeLinecap="round" opacity="0.78">
        <path d="M9.5 11.7 C10.7 10.95 12.8 10.85 14.1 11.45" />
        <path d="M21.9 11.45 C23.2 10.85 25.3 10.95 26.5 11.7" />
      </g>
    );
  }
  if (face.detail === "cheeks") {
    return (
      <g fill={colors.accent} opacity="0.42">
        <ellipse cx="9.25" cy="19.85" rx="2.35" ry="1.25" />
        <ellipse cx="26.75" cy="19.85" rx="2.35" ry="1.25" />
      </g>
    );
  }
  if (face.detail === "spark") {
    return (
      <g className={`${scope}-spark`} fill={colors.ink} opacity="0.55">
        <path d="M27.6 10.6 L28.2 12 L29.6 12.6 L28.2 13.2 L27.6 14.6 L27 13.2 L25.6 12.6 L27 12Z" />
      </g>
    );
  }
  if (face.detail === "mole") {
    return <circle cx="23.9" cy="20.25" r="0.55" fill={colors.ink} opacity="0.65" />;
  }
  return null;
}

function OperatorAvatarSvg({
  avatar,
  size = 40,
  className,
}: {
  avatar: AvatarOption;
  size?: number;
  className?: string;
}) {
  const instanceId = useId().replace(/:/g, "");
  const maskId = `avatar-mask-${avatar.id}-${instanceId}`;
  const clipId = `avatar-clip-${avatar.id}-${instanceId}`;
  const scope = `avatar-${avatar.id}-${instanceId}`;
  return (
    <svg
      viewBox="0 0 36 36"
      fill="none"
      role="img"
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      aria-label={avatar.alt}
      className={className}
    >
      <style>{avatarMotionStyles(scope, avatar.face)}</style>
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="36" height="36">
          <rect width="36" height="36" rx="18" fill="#fff" />
        </mask>
        <clipPath id={clipId}>
          <rect width="36" height="36" rx="18" />
        </clipPath>
      </defs>
      <g mask={`url(#${maskId})`} clipPath={`url(#${clipId})`}>
        <rect width="36" height="36" fill={avatar.colors.base} />
        <g className={`${scope}-accent`}>
          <rect
            x="-3"
            y="4"
            width="42"
            height="20"
            rx="8"
            transform="rotate(-24 18 18)"
            fill={avatar.colors.accent}
            opacity="0.92"
          />
          <circle cx="28" cy="7" r="8" fill={avatar.colors.ink} opacity="0.18" />
          <circle cx="9" cy="29" r="9" fill={avatar.colors.ink} opacity="0.14" />
        </g>
        <g className={`${scope}-face`}>
          <g transform="translate(0 1)">
            {renderDetails(avatar, scope)}
            {renderEyes(avatar, scope)}
            <path d="M18.1 17.2 C17.5 18.2 17.55 19.1 18.35 19.7" stroke={avatar.colors.ink} strokeWidth="0.85" strokeLinecap="round" fill="none" opacity="0.32" />
            {renderMouth(avatar)}
          </g>
        </g>
      </g>
    </svg>
  );
}

export function OperatorAvatar({
  avatarId,
  size = 40,
  className,
}: {
  avatarId?: string | null;
  size?: number;
  className?: string;
}) {
  return <OperatorAvatarSvg avatar={getAvatarOption(avatarId)} size={size} className={className} />;
}

export function AvatarPicker({
  value,
  onChange,
  displayName = "Me",
  subtitle = "Select your avatar",
  className,
  showPreview = true,
}: AvatarPickerProps) {
  const selectedAvatar = useMemo(() => getAvatarOption(value), [value]);

  return (
    <section className={cn("flex min-w-0 flex-col gap-4", className)}>
      {showPreview ? (
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[var(--border-subtle)] bg-[var(--panel-soft)]">
            <OperatorAvatarSvg avatar={selectedAvatar} size={64} />
          </span>
          <div className="min-w-0">
            <h2 className="m-0 truncate text-[1rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
              {displayName}
            </h2>
            <p className="m-0 mt-1 truncate text-[0.75rem] text-[var(--text-tertiary)]">
              {selectedAvatar.label}
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-5 gap-2" role="radiogroup" aria-label={subtitle}>
        {avatarOptions.map((avatar) => {
          const selected = selectedAvatar.id === avatar.id;
          return (
            <button
              key={avatar.id}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={`Select ${avatar.label}`}
              onClick={() => onChange?.(avatar.id)}
              className={cn(
                "relative flex h-10 w-full items-center justify-center overflow-hidden rounded-[var(--radius-panel-sm)] border bg-[var(--panel-soft)] transition-[border-color,background-color] duration-[120ms]",
                selected
                  ? "border-[var(--text-primary)] bg-[var(--surface-hover)]"
                  : "border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)]",
              )}
            >
              <OperatorAvatarSvg avatar={avatar} size={28} />
              {selected ? (
                <span className="absolute right-0.5 top-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--text-primary)] text-[var(--canvas)]">
                  <Check className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
