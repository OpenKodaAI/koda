import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { InsecureTransportScreen } from "@/components/auth/insecure-transport-screen";
import { SetupScreen } from "@/components/setup/setup-screen";
import { getControlPlaneAuthStatus } from "@/lib/control-plane";
import { insecureCookieTransport } from "@/lib/cookie-transport";
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
  // Over plain HTTP from a non-loopback host the browser drops the Secure
  // session cookie: creating the owner here would spend the setup code for a
  // session that is thrown away. Explain on this page instead of redirecting
  // to /login and back (J-14).
  const insecureTransport = insecureCookieTransport(await headers());
  if (insecureTransport) {
    return <InsecureTransportScreen origin={insecureTransport.origin} />;
  }

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
  } catch {
    // Whatever the failure, a browser that has seen an owner goes to sign-in;
    // any other gets the first-run screen, which re-checks on submit.
    if (hasOwnerHint) {
      redirect(loginTarget(nextParam));
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
