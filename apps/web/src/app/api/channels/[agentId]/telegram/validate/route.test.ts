import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("telegram validate route hardening", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("rejects an invalid legacy token format before calling Telegram", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { POST } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/channels/agent-1/telegram/validate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ token: "not-a-telegram-token" }),
      }),
    );

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      ok: false,
      error: "Invalid Telegram bot token format",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid AGENT_TOKEN format before calling Telegram", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { POST } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/channels/agent-1/telegram/validate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          credentials: {
            AGENT_TOKEN: "123456:too-short",
          },
        }),
      }),
    );

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      ok: false,
      error: "Invalid Telegram bot token format",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("still reaches Telegram for a syntactically valid token", async () => {
    const token = "123456:abcdefghijklmnopqrstuvwxyz";
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(`https://api.telegram.org/bot${token}/getMe`);
      return new Response(
        JSON.stringify({
          ok: true,
          result: {
            username: "koda_bot",
            first_name: "Koda Bot",
          },
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const { POST } = await import("./route");
    const response = await POST(
      new Request("http://localhost/api/channels/agent-1/telegram/validate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          credentials: {
            AGENT_TOKEN: token,
          },
        }),
      }),
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      ok: true,
      bot_username: "koda_bot",
      bot_name: "Koda Bot",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
