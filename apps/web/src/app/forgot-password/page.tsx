import { redirect } from "next/navigation";
import { ForgotPasswordScreen } from "@/components/auth/forgot-password-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function ForgotPasswordPage() {
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
  }
  return <ForgotPasswordScreen />;
}
