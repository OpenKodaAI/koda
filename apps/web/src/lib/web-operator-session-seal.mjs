/**
 * Seals the operator session token into the value of the session cookie and
 * opens it again: AES-256-GCM under a key derived from
 * WEB_OPERATOR_SESSION_SECRET. Plain ESM, so server.mjs checks the cookie on a
 * runtime relay upgrade with the same code the Next.js routes and proxy use
 * through web-operator-session.ts.
 */

import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

export const WEB_OPERATOR_SESSION_COOKIE = "koda_operator_session";

// Prefix of every credential placeholder shipped in .env.example. An unedited
// placeholder is publicly known, so it is treated as "not configured".
const PLACEHOLDER_SECRET_PREFIX = "replace-with-";

/**
 * The cookie key. Throws when WEB_OPERATOR_SESSION_SECRET is missing or still
 * the placeholder, unless an ephemeral dev-only key is allowed. The ephemeral
 * key lives on globalThis so server.mjs and the Next.js bundle, which load
 * this module separately in one process, share it.
 * @returns {Buffer}
 */
export function getSessionSecret() {
  const rawSecret = process.env.WEB_OPERATOR_SESSION_SECRET?.trim();
  const configuredSecret =
    rawSecret && !rawSecret.toLowerCase().startsWith(PLACEHOLDER_SECRET_PREFIX) ? rawSecret : "";
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
      "WEB_OPERATOR_SESSION_SECRET must be configured with a random value (the .env.example placeholder is rejected). To allow an ephemeral dev-only secret, set ALLOW_INSECURE_WEB_OPERATOR_SESSION_SECRET=true outside production.",
    );
  }

  if (!globalThis.__kodaWebOperatorSessionSecret) {
    globalThis.__kodaWebOperatorSessionSecret = { key: randomBytes(32) };
  }

  return globalThis.__kodaWebOperatorSessionSecret.key;
}

/**
 * @param {string} token
 * @returns {string} the cookie value, or "" for an empty token
 */
export function sealWebOperatorToken(token) {
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

/**
 * @param {string} value a cookie value
 * @returns {string | null} the token, or null when the value was not sealed
 *   under the current key (or no key is configured)
 */
export function unsealWebOperatorToken(value) {
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
