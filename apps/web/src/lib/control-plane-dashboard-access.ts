import "server-only";

import {
  type ControlPlaneAuthStatus,
  type ControlPlaneOnboardingStatus,
  getControlPlaneAuthStatus,
  getControlPlaneOnboardingStatus,
} from "@/lib/control-plane";

export type ControlPlaneDashboardAccessState =
  | {
      status: "ready";
      authStatus: ControlPlaneAuthStatus;
      onboardingStatus: ControlPlaneOnboardingStatus;
    }
  | {
      status: "setup_required";
      authStatus: ControlPlaneAuthStatus;
      onboardingStatus: ControlPlaneOnboardingStatus;
    }
  | {
      status: "unavailable";
      error: unknown;
    };

function normalizeNextTarget(rawTarget: string) {
  if (!rawTarget.startsWith("/") || rawTarget.startsWith("//")) {
    return null;
  }

  const parsed = new URL(rawTarget, "http://koda.local");
  if (parsed.origin !== "http://koda.local") {
    return null;
  }

  if (parsed.pathname !== "/control-plane" && !parsed.pathname.startsWith("/control-plane/")) {
    return null;
  }

  if (parsed.pathname === "/control-plane/setup" || parsed.pathname.startsWith("/control-plane/setup/")) {
    return null;
  }

  return `${parsed.pathname}${parsed.search}`;
}

export function sanitizeControlPlaneNextTarget(
  target: string | string[] | undefined,
): string | null {
  const candidate = Array.isArray(target) ? target[0] : target;
  const trimmed = candidate?.trim();
  if (!trimmed) {
    return null;
  }

  try {
    return normalizeNextTarget(trimmed);
  } catch {
    return null;
  }
}

export function buildControlPlaneSetupHref(nextTarget?: string | null) {
  const sanitized = sanitizeControlPlaneNextTarget(nextTarget ?? undefined);
  if (!sanitized) {
    return "/control-plane/setup";
  }
  return `/control-plane/setup?next=${encodeURIComponent(sanitized)}`;
}

export async function resolveControlPlaneDashboardAccess(): Promise<ControlPlaneDashboardAccessState> {
  try {
    const [authStatus, onboardingStatus] = await Promise.all([
      getControlPlaneAuthStatus(),
      getControlPlaneOnboardingStatus(),
    ]);

    if (authStatus.authenticated && onboardingStatus.steps.onboarding_complete) {
      return {
        status: "ready",
        authStatus,
        onboardingStatus,
      };
    }

    return {
      status: "setup_required",
      authStatus,
      onboardingStatus,
    };
  } catch (error) {
    return {
      status: "unavailable",
      error,
    };
  }
}
