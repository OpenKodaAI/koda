/**
 * Shared channel validation/status logic.
 *
 * Used by both the ``/api/channels/[agentId]/[channelType]/validate`` and
 * ``/api/channels/[agentId]/[channelType]/status`` routes so platform API
 * calls and response parsing are defined in exactly one place.
 */

import { controlPlaneFetch } from "@/lib/control-plane";

// ---------------------------------------------------------------------------
//  Fetch decrypted secrets from the control plane (server-side only)
// ---------------------------------------------------------------------------

export async function fetchChannelSecret(
  agentId: string,
  secretKey: string,
): Promise<string | null> {
  try {
    const res = await controlPlaneFetch(
      `/api/control-plane/agents/${encodeURIComponent(agentId)}/secrets/${encodeURIComponent(secretKey)}?include_value=true`,
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { value?: string };
    return data.value ?? null;
  } catch {
    return null;
  }
}

export async function fetchChannelSecrets(
  agentId: string,
  keys: string[],
): Promise<Record<string, string>> {
  const entries = await Promise.all(
    keys.map(async (key) => {
      const value = await fetchChannelSecret(agentId, key);
      return [key, value ?? ""] as const;
    }),
  );
  return Object.fromEntries(entries);
}

// ---------------------------------------------------------------------------
//  Types
// ---------------------------------------------------------------------------

export type ChannelCheckResult = {
  ok: boolean;
  display_name?: string;
  display_id?: string;
  error?: string;
};

// ---------------------------------------------------------------------------
//  Supported channels & secret keys
// ---------------------------------------------------------------------------

export const SUPPORTED_CHANNELS = new Set([
  "telegram",
  "whatsapp",
  "discord",
  "slack",
  "teams",
  "line",
  "messenger",
  "signal",
  "instagram",
]);

export const CHANNEL_SECRET_KEYS: Record<string, string[]> = {
  telegram: ["AGENT_TOKEN"],
  whatsapp: [
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
  ],
  discord: ["DISCORD_BOT_TOKEN"],
  slack: ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"],
  teams: ["TEAMS_APP_ID", "TEAMS_APP_PASSWORD"],
  line: ["LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"],
  messenger: [
    "MESSENGER_PAGE_ACCESS_TOKEN",
    "MESSENGER_VERIFY_TOKEN",
    "MESSENGER_APP_SECRET",
  ],
  signal: ["SIGNAL_PHONE_NUMBER", "SIGNAL_CLI_URL"],
  instagram: ["INSTAGRAM_PAGE_ACCESS_TOKEN", "INSTAGRAM_APP_SECRET"],
};

// ---------------------------------------------------------------------------
//  Per-channel checkers
// ---------------------------------------------------------------------------

async function checkTelegram(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const token = (credentials.AGENT_TOKEN ?? "").trim();
  if (!token) return { ok: false, error: "AGENT_TOKEN is required" };

  const res = await fetch(`https://api.telegram.org/bot${token}/getMe`);
  const data = (await res.json()) as {
    ok: boolean;
    description?: string;
    result?: { username?: string; first_name?: string };
  };

  if (!data.ok) return { ok: false, error: data.description ?? "Invalid token" };

  return {
    ok: true,
    display_name: data.result?.first_name ?? "",
    display_id: data.result?.username ?? "",
  };
}

async function checkWhatsapp(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const accessToken = (credentials.WHATSAPP_ACCESS_TOKEN ?? "").trim();
  const phoneNumberId = (credentials.WHATSAPP_PHONE_NUMBER_ID ?? "").trim();

  if (!accessToken || !phoneNumberId) {
    return {
      ok: false,
      error: "WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required",
    };
  }

  const res = await fetch(
    `https://graph.facebook.com/v21.0/${encodeURIComponent(phoneNumberId)}`,
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  const data = (await res.json()) as {
    display_phone_number?: string;
    verified_name?: string;
    error?: { message?: string };
  };

  if (!res.ok || data.error) {
    return {
      ok: false,
      error: data.error?.message ?? "Failed to validate WhatsApp credentials",
    };
  }

  return {
    ok: true,
    display_name: data.verified_name ?? "",
    display_id: data.display_phone_number ?? "",
  };
}

async function checkDiscord(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const token = (credentials.DISCORD_BOT_TOKEN ?? "").trim();
  if (!token) return { ok: false, error: "DISCORD_BOT_TOKEN is required" };

  const res = await fetch("https://discord.com/api/v10/users/@me", {
    headers: { Authorization: `Agent ${token}` },
  });
  const data = (await res.json()) as {
    username?: string;
    discriminator?: string;
    message?: string;
  };

  if (!res.ok) {
    return { ok: false, error: data.message ?? "Invalid Discord agent token" };
  }

  return {
    ok: true,
    display_name: data.username ?? "",
    display_id: data.discriminator ?? "",
  };
}

async function checkSlack(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const token = (credentials.SLACK_BOT_TOKEN ?? "").trim();
  if (!token) return { ok: false, error: "SLACK_BOT_TOKEN is required" };

  const res = await fetch("https://slack.com/api/auth.test", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = (await res.json()) as {
    ok: boolean;
    error?: string;
    bot_id?: string;
    user?: string;
    team?: string;
  };

  if (!data.ok) return { ok: false, error: data.error ?? "Invalid Slack agent token" };

  return {
    ok: true,
    display_name: data.user ?? "",
    display_id: data.team ?? "",
  };
}

async function checkTeams(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const appId = (credentials.TEAMS_APP_ID ?? "").trim();
  const appPassword = (credentials.TEAMS_APP_PASSWORD ?? "").trim();

  if (!appId || !appPassword) {
    return { ok: false, error: "TEAMS_APP_ID and TEAMS_APP_PASSWORD are required" };
  }

  const body = new URLSearchParams({
    grant_type: "client_credentials",
    client_id: appId,
    client_secret: appPassword,
    scope: "https://api.botframework.com/.default",
  });

  const res = await fetch(
    "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    },
  );
  const data = (await res.json()) as {
    access_token?: string;
    error?: string;
    error_description?: string;
  };

  if (!res.ok || !data.access_token) {
    return {
      ok: false,
      error: data.error_description ?? data.error ?? "Invalid Teams credentials",
    };
  }

  return { ok: true, display_name: "Teams Agent", display_id: appId };
}

async function checkLine(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const token = (credentials.LINE_CHANNEL_ACCESS_TOKEN ?? "").trim();
  if (!token) return { ok: false, error: "LINE_CHANNEL_ACCESS_TOKEN is required" };

  const res = await fetch("https://api.line.me/v2/bot/info", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = (await res.json()) as {
    displayName?: string;
    userId?: string;
    basicId?: string;
    message?: string;
  };

  if (!res.ok) {
    return { ok: false, error: data.message ?? "Invalid LINE channel access token" };
  }

  return {
    ok: true,
    display_name: data.displayName ?? "",
    display_id: data.basicId ?? data.userId ?? "",
  };
}

async function checkMessenger(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const token = (credentials.MESSENGER_PAGE_ACCESS_TOKEN ?? "").trim();
  if (!token) return { ok: false, error: "MESSENGER_PAGE_ACCESS_TOKEN is required" };

  const res = await fetch(
    "https://graph.facebook.com/v21.0/me?fields=name",
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const data = (await res.json()) as {
    name?: string;
    id?: string;
    error?: { message?: string };
  };

  if (!res.ok || data.error) {
    return {
      ok: false,
      error: data.error?.message ?? "Invalid Messenger page access token",
    };
  }

  return { ok: true, display_name: data.name ?? "", display_id: data.id ?? "" };
}

function isPrivateUrl(raw: string): boolean {
  try {
    const url = new URL(raw);
    const host = url.hostname.toLowerCase();
    if (["localhost", "127.0.0.1", "::1", "0.0.0.0"].includes(host)) return true;
    if (host.startsWith("169.254.")) return true;
    if (host.startsWith("10.")) return true;
    if (host.startsWith("192.168.")) return true;
    if (/^172\.(1[6-9]|2\d|3[01])\./.test(host)) return true;
    if (!["http:", "https:"].includes(url.protocol)) return true;
    return false;
  } catch {
    return true;
  }
}

async function checkSignal(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const signalCliUrl = (credentials.SIGNAL_CLI_URL ?? "").trim();
  const phoneNumber = (credentials.SIGNAL_PHONE_NUMBER ?? "").trim();

  if (!signalCliUrl) return { ok: false, error: "SIGNAL_CLI_URL is required" };
  if (!phoneNumber) return { ok: false, error: "SIGNAL_PHONE_NUMBER is required" };
  if (isPrivateUrl(signalCliUrl)) {
    return { ok: false, error: "SIGNAL_CLI_URL must be a public HTTPS URL" };
  }

  const res = await fetch(`${signalCliUrl}/v1/about`);
  if (!res.ok) return { ok: false, error: "signal-cli REST API is not reachable" };

  return { ok: true, display_name: phoneNumber, display_id: phoneNumber };
}

async function checkInstagram(
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const token = (credentials.INSTAGRAM_PAGE_ACCESS_TOKEN ?? "").trim();
  if (!token) return { ok: false, error: "INSTAGRAM_PAGE_ACCESS_TOKEN is required" };

  const res = await fetch(
    "https://graph.facebook.com/v21.0/me?fields=name,username",
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const data = (await res.json()) as {
    name?: string;
    username?: string;
    id?: string;
    error?: { message?: string };
  };

  if (!res.ok || data.error) {
    return {
      ok: false,
      error: data.error?.message ?? "Invalid Instagram page access token",
    };
  }

  return {
    ok: true,
    display_name: data.name ?? "",
    display_id: data.username ?? data.id ?? "",
  };
}

// ---------------------------------------------------------------------------
//  Dispatcher
// ---------------------------------------------------------------------------

const CHECKERS: Record<
  string,
  (credentials: Record<string, string>) => Promise<ChannelCheckResult>
> = {
  telegram: checkTelegram,
  whatsapp: checkWhatsapp,
  discord: checkDiscord,
  slack: checkSlack,
  teams: checkTeams,
  line: checkLine,
  messenger: checkMessenger,
  signal: checkSignal,
  instagram: checkInstagram,
};

/**
 * Validate/check credentials for the given channel type.
 * Used by both the validate (user-provided creds) and status (stored creds) routes.
 */
export async function checkChannel(
  channelType: string,
  credentials: Record<string, string>,
): Promise<ChannelCheckResult> {
  const checker = CHECKERS[channelType];
  if (!checker) {
    return { ok: false, error: `No checker for channel type: ${channelType}` };
  }
  return checker(credentials);
}
