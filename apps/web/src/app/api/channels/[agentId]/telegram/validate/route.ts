import { NextResponse } from "next/server";

const TELEGRAM_BOT_TOKEN_RE = /^\d{6,}:[A-Za-z0-9_-]{20,}$/;

export async function POST(request: Request) {
  let token: string;
  try {
    const body = (await request.json()) as {
      token?: string;
      credentials?: Record<string, string>;
    };
    // Accept both legacy { token } and generic { credentials: { AGENT_TOKEN } }
    token = (body.token ?? body.credentials?.AGENT_TOKEN ?? "").trim();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid request body" },
      { status: 400 },
    );
  }

  if (!token) {
    return NextResponse.json(
      { ok: false, error: "Token is required" },
      { status: 400 },
    );
  }

  if (!TELEGRAM_BOT_TOKEN_RE.test(token)) {
    return NextResponse.json(
      { ok: false, error: "Invalid Telegram bot token format" },
      { status: 400 },
    );
  }

  let telegramData: {
    ok: boolean;
    description?: string;
    result?: { username?: string; first_name?: string };
  };
  try {
    const telegramRes = await fetch(`https://api.telegram.org/bot${token}/getMe`);
    telegramData = (await telegramRes.json()) as typeof telegramData;
  } catch {
    return NextResponse.json(
      { ok: false, error: "Failed to reach Telegram API" },
      { status: 502 },
    );
  }

  if (!telegramData.ok) {
    return NextResponse.json(
      { ok: false, error: telegramData.description || "Invalid token" },
      { status: 400 },
    );
  }

  return NextResponse.json({
    ok: true,
    bot_username: telegramData.result?.username ?? "",
    bot_name: telegramData.result?.first_name ?? "",
  });
}
