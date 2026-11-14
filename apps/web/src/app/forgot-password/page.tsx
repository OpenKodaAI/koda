import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { ForgotPasswordScreen } from "@/components/auth/forgot-password-screen";
import { InsecureTransportScreen } from "@/components/auth/insecure-transport-screen";
import { ControlPlaneRequestError, getControlPlaneAuthStatus } from "@/lib/control-plane";
import { insecureCookieTransport } from "@/lib/cookie-transport";
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
  // Over plain HTTP from a non-loopback host the recovery code and the new
  // password would cross the network in clear text, every session would be
  // revoked, and the operator would land on a /login that cannot sign in from
  // this browser. Explain instead of taking the code (J-14).
  const insecureTransport = insecureCookieTransport(await headers());
  if (insecureTransport) {
    return <InsecureTransportScreen origin={insecureTransport.origin} />;
  }

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
