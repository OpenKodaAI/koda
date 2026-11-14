import { describe, expect, it } from "vitest";

import { rateLimitedAuthMessage } from "@/lib/auth-rate-limit-message";
import { ApiError } from "@/lib/errors";
import { translateForLanguage } from "@/lib/i18n";

const t = (key: string, options?: Record<string, unknown>) => translateForLanguage("en-US", key, options);

const throttled = (retryAfterSeconds: number | null) =>
  new ApiError("Too many attempts. Try again later.", 429, { retryAfterSeconds });

describe("rateLimitedAuthMessage", () => {
  it.each([
    [30, "Too many attempts. Wait 30 seconds and try again."],
    [120, "Too many attempts. Wait 2 minutes and try again."],
    [360, "Too many attempts. Wait 6 minutes and try again."],
  ])("names the wait a Retry-After of %i asks for", (seconds, message) => {
    expect(rateLimitedAuthMessage(throttled(seconds), t, "en-US")).toBe(message);
  });

  // `Retry-After: 0`, or an HTTP-date already past, means the client may retry now.
  it.each([null, 0])("asks to wait a moment when the wait is %j", (seconds) => {
    expect(rateLimitedAuthMessage(throttled(seconds), t, "en-US")).toBe(
      "Too many attempts. Wait a moment and try again.",
    );
  });

  it.each([
    ["a rejected attempt", new ApiError("Invalid credentials.", 400)],
    ["an auth failure", new ApiError("Invalid credentials.", 401)],
    ["an upstream failure", new ApiError("Service unavailable", 503)],
    ["a network failure", new TypeError("Failed to fetch")],
  ])("leaves %s to the screen's own message", (_name, error) => {
    expect(rateLimitedAuthMessage(error, t, "en-US")).toBeNull();
  });
});
