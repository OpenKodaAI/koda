import { NextResponse } from "next/server";
import {
  CHANNEL_SECRET_KEYS,
  checkChannel,
  fetchChannelSecret,
  fetchChannelSecrets,
} from "@/lib/channel-validators";

// ---------------------------------------------------------------------------
//  Resolve Telegram allowed user IDs to display names
// ---------------------------------------------------------------------------

async function resolveAllowedUsers(
  token: string,
  rawIds: string,
): Promise<{ id: string; name: string }[]> {
  const ids = rawIds.split(",").map((s) => s.trim()).filter(Boolean);

  return Promise.all(
    ids.map(async (uid) => {
      const entry: { id: string; name: string } = { id: uid, name: "" };
      try {
        const res = await fetch(
          `https://api.telegram.org/bot${token}/getChat?chat_id=${encodeURIComponent(uid)}`,
          { signal: AbortSignal.timeout(5000) },
        );
        if (res.ok) {
          const data = (await res.json()) as {
            ok?: boolean;
            result?: { first_name?: string; last_name?: string; username?: string };
          };
          if (data.ok && data.result) {
            const parts = [data.result.first_name ?? "", data.result.last_name ?? ""];
            const display = parts.filter(Boolean).join(" ") || uid;
            const username = data.result.username ?? "";
            entry.name = username ? `@${username}` : display;
          }
        }
      } catch {
        // Ignore per-user resolution failures
      }
      return entry;
    }),
  );
}

// ---------------------------------------------------------------------------
//  Route handler
// ---------------------------------------------------------------------------

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ agentId: string }> },
) {
  const { agentId } = await params;

  const secretKeys = CHANNEL_SECRET_KEYS.telegram;
  if (!secretKeys) {
    return NextResponse.json(
      { ok: false, error: "Unsupported channel type: telegram" },
      { status: 400 },
    );
  }

  try {
    const credentials = await fetchChannelSecrets(agentId, secretKeys);
    const result = await checkChannel("telegram", credentials);

    if (!result.ok) {
      return NextResponse.json(result, { status: 400 });
    }

    // Resolve allowed users (Telegram-specific feature)
    const token = credentials.AGENT_TOKEN ?? "";
    const allowedRaw = await fetchChannelSecret(agentId, "ALLOWED_USER_IDS");
    const allowed_users = allowedRaw
      ? await resolveAllowedUsers(token, allowedRaw)
      : [];

    return NextResponse.json({
      ...result,
      // Include legacy field names for backward compatibility
      bot_username: result.display_id ?? "",
      bot_name: result.display_name ?? "",
      allowed_users,
    });
  } catch {
    return NextResponse.json(
      { ok: false, error: "Failed to check telegram status" },
      { status: 502 },
    );
  }
}
