import "server-only";

import { cache } from "react";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import {
  ControlPlaneRequestError,
  getControlPlaneAuthStatus,
  type ControlPlaneAuthStatus,
} from "@/lib/control-plane";
import { isSafeRedirectTarget } from "@/lib/safe-redirect";

export type AuthenticatedSession = {
  status: ControlPlaneAuthStatus;
  operator: NonNullable<ControlPlaneAuthStatus["operator"]>;
};

async function readSafeNextFromHeaders(): Promise<string | null> {
  const store = await headers();
  const pathname = store.get("x-koda-pathname") || "";
  return isSafeRedirectTarget(pathname) ? pathname : null;
}

function redirectToLogin(safeNext: string | null): never {
  const target = safeNext
    ? `/login?next=${encodeURIComponent(safeNext)}`
    : "/login";
  redirect(target);
}

/**
 * Server-only authentication gate, deduped per request via React cache(). Use
 * from layouts/pages that must be reached only by signed-in operators. The
 * proxy already redirects unauthenticated traffic at the network boundary;
 * this is the second layer that revalidates the cryptographic claim against
 * the control plane (so a sealed-but-revoked cookie cannot reach the app).
 *
 * Behavior:
 * - 401 from /auth/status, or `authenticated: false` → redirect to
 *   `/login?next=<safe-current-path>`.
 * - Any other upstream error (5xx, network) → re-throws so error.tsx renders
 *   instead of a redirect loop while the control plane is unreachable.
 */
export const requireAuthenticatedSession = cache(
  async (): Promise<AuthenticatedSession> => {
    const safeNext = await readSafeNextFromHeaders();
    let status: ControlPlaneAuthStatus;
    try {
      status = await getControlPlaneAuthStatus();
    } catch (error) {
      if (error instanceof ControlPlaneRequestError && error.status === 401) {
        redirectToLogin(safeNext);
      }
      throw error;
    }
    if (!status.authenticated || !status.operator) {
      redirectToLogin(safeNext);
    }
    return { status, operator: status.operator };
  },
);

/**
 * Tagged union of every state the SSR layout actually needs to differentiate:
 *
 * - `ok`             → control plane responded; `status.authenticated`
 *                      tells you whether to render the app shell or kick to
 *                      `/login`.
 * - `unauthenticated` → control plane explicitly said "no session" (401). The
 *                      sealed cookie is gone or revoked server-side, redirect
 *                      to `/login`.
 * - `unreachable`     → control plane returned 503 / timed out / refused the
 *                      connection. We don't actually know whether the cookie
 *                      is valid — but we DO know we shouldn't punish the user
 *                      with a logout because the backend hiccuped. Layouts
 *                      keep rendering and let the client retry on focus.
 */
export type AuthStatusResolution =
  | { kind: "ok"; status: ControlPlaneAuthStatus }
  | { kind: "unauthenticated" }
  | { kind: "unreachable"; cause: unknown };

/**
 * Read the auth status without enforcing authentication. Returns the typed
 * union so layouts can differentiate "user has no session" from "control
 * plane is napping" — collapsing both into `null` (the previous behaviour)
 * forced a `/login` redirect on every transient upstream blip and felt like
 * the operator was being logged out repeatedly.
 */
export const resolveOptionalAuthStatus = cache(
  async (): Promise<AuthStatusResolution> => {
    try {
      // SSR layout probe — keep it short. The proxy already validated the
      // sealed cookie shape; here we're just confirming the backend hasn't
      // revoked it. 3s is enough for a healthy backend and short enough to
      // not freeze every navigation when the backend is misbehaving.
      const status = await getControlPlaneAuthStatus({ timeoutMs: 3000 });
      return { kind: "ok", status };
    } catch (error) {
      if (error instanceof ControlPlaneRequestError) {
        if (error.status === 401) {
          return { kind: "unauthenticated" };
        }
        // 5xx, 503, network failure, timeout — anything that isn't a clean
        // "no session" answer. Trust the cookie shape verified by the proxy
        // and let the page render.
        return { kind: "unreachable", cause: error };
      }
      throw error;
    }
  },
);

/**
 * Backwards-compatible thin wrapper. New call sites should prefer
 * `resolveOptionalAuthStatus` so they can react to upstream-unreachable
 * without bouncing the operator to `/login`.
 */
export const getOptionalAuthStatus = cache(
  async (): Promise<ControlPlaneAuthStatus | null> => {
    const resolution = await resolveOptionalAuthStatus();
    return resolution.kind === "ok" ? resolution.status : null;
  },
);
