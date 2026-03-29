import { describe, expect, it } from "vitest";
import { middleware } from "./middleware";

describe("web middleware auth gate", () => {
  it("blocks proxy routes without an operator session", () => {
    const response = middleware({
      nextUrl: new URL("http://localhost/api/control-plane/agents"),
      cookies: {
        get: () => undefined,
      },
    } as never);

    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("allows proxy routes when an operator session cookie exists", () => {
    const response = middleware({
      nextUrl: new URL("http://localhost/api/control-plane/agents"),
      cookies: {
        get: () => ({ value: "sealed-session" }),
      },
    } as never);

    expect(response.status).toBe(200);
  });
});
