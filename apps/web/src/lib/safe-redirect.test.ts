import { describe, expect, it } from "vitest";
import { isSafeRedirectTarget, safeRedirectTarget } from "@/lib/safe-redirect";

describe("isSafeRedirectTarget", () => {
  it.each([
    ["/sessions"],
    ["/sessions/abc"],
    ["/control-plane/agents/x"],
    ["/memory?filter=tags"],
    ["/"],
  ])("accepts %s", (value) => {
    expect(isSafeRedirectTarget(value)).toBe(true);
  });

  it.each([
    ["//evil.com"],
    ["http://evil.com"],
    ["https://evil.com"],
    ["javascript:alert(1)"],
    ["/api/secret"],
    ["/oauth/callback"],
    ["/_next/static/chunks/x.js"],
    ["mailto:foo@bar"],
    [""],
    [null],
    [undefined],
    ["sessions"], // missing leading slash
    ["/sessions#evil"], // fragments are stripped client-side; reject embedded
  ])("rejects %s", (value) => {
    expect(isSafeRedirectTarget(value as string | null | undefined)).toBe(false);
  });
});

describe("safeRedirectTarget", () => {
  it("returns the value when safe", () => {
    expect(safeRedirectTarget("/sessions")).toBe("/sessions");
  });

  it("returns the fallback when unsafe", () => {
    expect(safeRedirectTarget("//evil.com")).toBe("/");
    expect(safeRedirectTarget("/api/secret")).toBe("/");
    expect(safeRedirectTarget(null)).toBe("/");
  });

  it("respects a custom fallback", () => {
    expect(safeRedirectTarget("//evil.com", "/dashboard")).toBe("/dashboard");
  });
});
