import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SetupScreen } from "@/components/setup/setup-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";
import { isSafeRedirectTarget, safeRedirectTarget } from "@/lib/safe-redirect";
import {
  OWNER_EXISTS_HINT_COOKIE,
  PENDING_RECOVERY_COOKIE,
} from "@/lib/web-operator-session-constants";

export const dynamic = "force-dynamic";

type SetupPageProps = {
  searchParams: Promise<{ next?: string | string[] }>;
};

function pickNext(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

function loginTarget(nextParam: string | null): string {
  return isSafeRedirectTarget(nextParam)
    ? `/login?next=${encodeURIComponent(nextParam)}`
    : "/login";
}

export default async function SetupPage({ searchParams }: SetupPageProps) {
  const params = await searchParams;
  const nextParam = pickNext(params?.next);
  const store = await cookies();
  const hasOwnerHint = store.get(OWNER_EXISTS_HINT_COOKIE)?.value === "1";
  const hasPendingRecovery = store.get(PENDING_RECOVERY_COOKIE)?.value === "1";
  let authStatus;

  try {
    // This page decides whether owner creation is even allowed. Give the
    // control plane enough room on a cold dev stack so returning users are not
    // shown the first-run form by accident.
    authStatus = await getControlPlaneAuthStatus({ timeoutMs: 5000 });
  } catch (error) {
    if (hasOwnerHint) {
      redirect(loginTarget(nextParam));
    }
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      return <SetupScreen authStatus={null} />;
    }
    return <SetupScreen authStatus={null} />;
  }

  if (authStatus.authenticated) {
    if (hasPendingRecovery) {
      // Let the client finish the recovery-codes step; it re-hydrates codes
      // from sessionStorage and calls /auth/recovery-codes/acknowledge on
      // confirmation, which clears the marker cookie.
      return <SetupScreen authStatus={authStatus} />;
    }
    redirect(safeRedirectTarget(nextParam));
  }
  if (authStatus.has_owner) {
    // Owner already exists — send returning user to /login. The
    // `koda_has_owner` hint cookie is set by the /api/control-plane/[...path]
    // proxy when it observes has_owner=true from the control plane.
    redirect(loginTarget(nextParam));
  }

  return <SetupScreen authStatus={authStatus} />;
}
