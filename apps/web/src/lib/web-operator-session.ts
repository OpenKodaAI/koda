import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

import { cookies } from "next/headers";
import type { NextResponse } from "next/server";

const WEB_OPERATOR_SESSION_COOKIE = "koda_operator_session";
const WEB_OPERATOR_SESSION_MAX_AGE_SECONDS = 60 * 60 * 8;

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

export function setWebOperatorSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set({
    name: WEB_OPERATOR_SESSION_COOKIE,
    value: sealWebOperatorToken(token),
    httpOnly: true,
    sameSite: "lax",
    maxAge: WEB_OPERATOR_SESSION_MAX_AGE_SECONDS,
    path: "/",
    secure: process.env.NODE_ENV === "production",
  });
}

export function clearWebOperatorSessionCookie(response: NextResponse): void {
  response.cookies.set({
    name: WEB_OPERATOR_SESSION_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    maxAge: 0,
    path: "/",
    secure: process.env.NODE_ENV === "production",
  });
}
