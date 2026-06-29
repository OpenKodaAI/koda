import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { LoginScreen } from "@/components/auth/login-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";
import { safeRedirectTarget } from "@/lib/safe-redirect";
import { WEB_OPERATOR_SESSION_COOKIE } from "@/lib/web-operator-session-constants";

export const dynamic = "force-dynamic";

type LoginPageProps = {
  searchParams: Promise<{ next?: string | string[] }>;
};

function pickNext(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const nextParam = pickNext(params?.next);

  // Skip the auth-status probe entirely when no session cookie is present —
  // the user can't be "already signed in" without one, so there's nothing to
  // verify. Saves the round-trip (and the 2s timeout cliff when the backend
  // is misbehaving) for the common case: unauthenticated visitor lands on
  // /login.
  const cookieStore = await cookies();
  const hasSessionCookie = Boolean(
    cookieStore.get(WEB_OPERATOR_SESSION_COOKIE)?.value?.trim(),
  );
  if (!hasSessionCookie) {
    return <LoginScreen />;
  }

  try {
    // Short timeout: this is a "are you already signed in?" probe, not the
    // login itself. If the control plane doesn't answer in 2s we paint the
    // form rather than making the operator wait through the 6s global ceiling.
    const status = await getControlPlaneAuthStatus({ timeoutMs: 2000 });
    if (status.authenticated) {
      redirect(safeRedirectTarget(nextParam));
    }
    if (!status.has_owner) {
      const target = nextParam
        ? `/setup?next=${encodeURIComponent(safeRedirectTarget(nextParam))}`
        : "/setup";
      redirect(target);
    }
  } catch (error) {
    if (!(error instanceof ControlPlaneRequestError)) {
      throw error;
    }
    // Control plane unreachable, timed out, or 401 — render the form anyway.
  }
  return <LoginScreen />;
}
