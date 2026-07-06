import { redirect } from "next/navigation";
import { ForgotPasswordScreen } from "@/components/auth/forgot-password-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";
import { safeRedirectTarget } from "@/lib/safe-redirect";

export const dynamic = "force-dynamic";

type ForgotPasswordPageProps = {
  searchParams: Promise<{ next?: string | string[] }>;
};

function pickNext(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

export default async function ForgotPasswordPage({ searchParams }: ForgotPasswordPageProps) {
  const params = await searchParams;
  const nextParam = pickNext(params?.next);
  try {
    const status = await getControlPlaneAuthStatus();
    if (status.authenticated) {
      redirect(safeRedirectTarget(nextParam));
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
