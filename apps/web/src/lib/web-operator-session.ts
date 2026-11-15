import "server-only";

import { cookies } from "next/headers";
import type { NextResponse } from "next/server";
import { secureCookiesEnabled } from "@/lib/cookie-transport";
import {
  OWNER_EXISTS_HINT_COOKIE,
  OWNER_EXISTS_HINT_MAX_AGE_SECONDS,
  PENDING_RECOVERY_COOKIE,
  PENDING_RECOVERY_MAX_AGE_SECONDS,
  WEB_OPERATOR_SESSION_COOKIE,
  WEB_OPERATOR_SESSION_MAX_AGE_SECONDS,
} from "@/lib/web-operator-session-constants";
import {
  getSessionSecret,
  sealWebOperatorToken,
  unsealWebOperatorToken,
} from "@/lib/web-operator-session-seal.mjs";

// The sealing code is shared with server.mjs, which checks the cookie on a
// runtime relay upgrade (runtime-relay-server.mjs).
export { sealWebOperatorToken, unsealWebOperatorToken };

/**
 * Throws when the session secret is missing or still the .env.example
 * placeholder. Call before any upstream request whose result must end up in a
 * session cookie, so a misconfiguration fails before the control plane acts
 * (e.g. before owner registration consumes the setup code).
 */
let sessionSecretErrorLogged = false;

export function assertWebOperatorSessionSecretConfigured(): void {
  try {
    getSessionSecret();
  } catch (error) {
    if (!sessionSecretErrorLogged) {
      sessionSecretErrorLogged = true;
      console.error("[web-operator-session]", error instanceof Error ? error.message : error);
    }
    throw error;
  }
}

export async function getWebOperatorTokenFromCookie(): Promise<string | null> {
  const cookieStore = await cookies();
  const sealed = cookieStore.get(WEB_OPERATOR_SESSION_COOKIE)?.value?.trim();
  if (!sealed) {
    return null;
  }
  return unsealWebOperatorToken(sealed);
}

export function setWebOperatorSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set({
    name: WEB_OPERATOR_SESSION_COOKIE,
    value: sealWebOperatorToken(token),
    httpOnly: true,
    sameSite: "strict",
    maxAge: WEB_OPERATOR_SESSION_MAX_AGE_SECONDS,
    path: "/",
    secure: secureCookiesEnabled(),
  });
}

export function clearWebOperatorSessionCookie(response: NextResponse): void {
  response.cookies.set({
    name: WEB_OPERATOR_SESSION_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    maxAge: 0,
    path: "/",
    secure: secureCookiesEnabled(),
  });
}

export function setOwnerExistsHintCookie(response: NextResponse, hasOwner: boolean): void {
  response.cookies.set({
    name: OWNER_EXISTS_HINT_COOKIE,
    value: hasOwner ? "1" : "",
    httpOnly: false,
    sameSite: "lax",
    maxAge: hasOwner ? OWNER_EXISTS_HINT_MAX_AGE_SECONDS : 0,
    path: "/",
    secure: secureCookiesEnabled(),
  });
}

export function setPendingRecoveryCookie(response: NextResponse, pending: boolean): void {
  response.cookies.set({
    name: PENDING_RECOVERY_COOKIE,
    value: pending ? "1" : "",
    httpOnly: true,
    sameSite: "strict",
    maxAge: pending ? PENDING_RECOVERY_MAX_AGE_SECONDS : 0,
    path: "/",
    secure: secureCookiesEnabled(),
  });
}

export function clearPendingRecoveryCookie(response: NextResponse): void {
  setPendingRecoveryCookie(response, false);
}
