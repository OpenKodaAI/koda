import { redirect } from "next/navigation";
import { LoginScreen } from "@/components/auth/login-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  try {
    const status = await getControlPlaneAuthStatus();
    if (status.authenticated) {
      redirect("/");
    }
    if (!status.has_owner) {
      redirect("/setup");
    }
  } catch (error) {
    if (!(error instanceof ControlPlaneRequestError)) {
      throw error;
    }
    // Control plane unreachable or 401 — render the login form anyway.
  }
  return <LoginScreen />;
}
