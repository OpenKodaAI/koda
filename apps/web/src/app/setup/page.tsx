import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SetupScreen } from "@/components/setup/setup-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";
import { PENDING_RECOVERY_COOKIE } from "@/lib/web-operator-session-constants";

export const dynamic = "force-dynamic";

export default async function SetupPage() {
  let authStatus;

  try {
    authStatus = await getControlPlaneAuthStatus();
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      return <SetupScreen authStatus={null} />;
    }
    return <SetupScreen authStatus={null} />;
  }

  const store = await cookies();
  const hasPendingRecovery = store.get(PENDING_RECOVERY_COOKIE)?.value === "1";

  if (authStatus.authenticated) {
    if (hasPendingRecovery) {
      // Let the client finish the recovery-codes step; it re-hydrates codes
      // from sessionStorage and calls /auth/recovery-codes/acknowledge on
      // confirmation, which clears the marker cookie.
      return <SetupScreen authStatus={authStatus} />;
    }
    redirect("/");
  }
  if (authStatus.has_owner) {
    // Owner already exists — send returning user to /login. The
    // `koda_has_owner` hint cookie is set by the /api/control-plane/[...path]
    // proxy when it observes has_owner=true from the control plane.
    redirect("/login");
  }

  return <SetupScreen authStatus={authStatus} />;
}
