import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

import { cookies } from "next/headers";
import type { NextResponse } from "next/server";
import {
  OWNER_EXISTS_HINT_COOKIE,
  OWNER_EXISTS_HINT_MAX_AGE_SECONDS,
  PENDING_RECOVERY_COOKIE,
  PENDING_RECOVERY_MAX_AGE_SECONDS,
  WEB_OPERATOR_SESSION_COOKIE,
  WEB_OPERATOR_SESSION_MAX_AGE_SECONDS,
} from "@/lib/web-operator-session-constants";

type SessionSecretState = {
  key: Buffer;
};

declare global {
  var __kodaWebOperatorSessionSecret: SessionSecretState | undefined;
}

function getSessionSecret(): Buffer {
  const configuredSecret = process.env.WEB_OPERATOR_SESSION_SECRET?.trim();
  if (configuredSecret) {
    return createHash("sha256").update(configuredSecret).digest();
  }

  if (process.env.NODE_ENV === "test") {
    return createHash("sha256").update("koda-test-web-operator-session").digest();
  }

  const allowEphemeralSessionSecret =
    process.env.NODE_ENV !== "production" &&
    String(process.env.ALLOW_INSECURE_WEB_OPERATOR_SESSION_SECRET)
      .trim()
      .toLowerCase() === "true";
  if (!allowEphemeralSessionSecret) {
    throw new Error(
      "WEB_OPERATOR_SESSION_SECRET must be configured. To allow an ephemeral dev-only secret, set ALLOW_INSECURE_WEB_OPERATOR_SESSION_SECRET=true outside production.",
    );
  }

  if (!globalThis.__kodaWebOperatorSessionSecret) {
    globalThis.__kodaWebOperatorSessionSecret = { key: randomBytes(32) };
  }

  return globalThis.__kodaWebOperatorSessionSecret.key;
}

export function sealWebOperatorToken(token: string): string {
  const plaintext = Buffer.from(String(token || "").trim(), "utf-8");
  if (!plaintext.length) {
    return "";
  }

  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", getSessionSecret(), iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [iv, ciphertext, tag].map((part) => part.toString("base64url")).join(".");
}

export function unsealWebOperatorToken(value: string): string | null {
  const parts = String(value || "").trim().split(".");
  if (parts.length !== 3) {
    return null;
  }

  try {
    const [ivPart, ciphertextPart, tagPart] = parts;
    const iv = Buffer.from(ivPart, "base64url");
    const ciphertext = Buffer.from(ciphertextPart, "base64url");
    const tag = Buffer.from(tagPart, "base64url");
    const decipher = createDecipheriv("aes-256-gcm", getSessionSecret(), iv);
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf-8").trim();
  } catch {
    return null;
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

const ALLOW_INSECURE_COOKIES =
  process.env.NODE_ENV !== "production" &&
  String(process.env.ALLOW_INSECURE_COOKIES).trim().toLowerCase() === "true";
const SECURE_COOKIES =
  !ALLOW_INSECURE_COOKIES &&
  (
    process.env.NODE_ENV === "production" ||
    String(process.env.SECURE_COOKIES).trim().toLowerCase() === "true"
  );

export function setWebOperatorSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set({
    name: WEB_OPERATOR_SESSION_COOKIE,
    value: sealWebOperatorToken(token),
    httpOnly: true,
    sameSite: "strict",
    maxAge: WEB_OPERATOR_SESSION_MAX_AGE_SECONDS,
    path: "/",
    secure: SECURE_COOKIES,
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
    secure: SECURE_COOKIES,
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
    secure: SECURE_COOKIES,
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
    secure: SECURE_COOKIES,
  });
}

export function clearPendingRecoveryCookie(response: NextResponse): void {
  setPendingRecoveryCookie(response, false);
}
