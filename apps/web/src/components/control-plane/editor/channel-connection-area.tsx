"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  IntegrationCardStatusIndicator,
} from "@/components/control-plane/system/integrations/integration-card-presentation";
import {
  CHANNEL_CATALOG,
  type ChannelDefinition,
  type ChannelStatus,
} from "./channel-catalog-data";
import { ChannelConnectionModal } from "@/components/control-plane/editor/channel-connection-modal";

/* ------------------------------------------------------------------ */
/*  Channel inline SVG logos                                           */
/* ------------------------------------------------------------------ */

function TelegramLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  );
}

function WhatsAppLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />
    </svg>
  );
}

function DiscordLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
    </svg>
  );
}

function SlackLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z" />
    </svg>
  );
}

function TeamsLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M21.168 2.496A3.12 3.12 0 0 0 18.72.72L6.48.048A3.12 3.12 0 0 0 3.36 2.496L.048 18.72A3.12 3.12 0 0 0 2.496 21.84l12.24.672a3.12 3.12 0 0 0 3.12-2.448l3.312-16.224a3.12 3.12 0 0 0-1.344-1.344zM15.36 7.2h-3.12v9.6h-2.4V7.2H6.72V5.04h8.64V7.2z" />
    </svg>
  );
}

function LineLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M19.365 9.863c.349 0 .63.285.63.631 0 .345-.281.63-.63.63H17.61v1.125h1.755c.349 0 .63.283.63.63 0 .344-.281.629-.63.629h-2.386c-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63h2.386c.346 0 .627.285.627.63 0 .349-.281.63-.63.63H17.61v1.125h1.755zm-3.855 3.016c0 .27-.174.51-.432.596-.064.021-.133.031-.199.031-.211 0-.391-.09-.51-.25l-2.443-3.317v2.94c0 .344-.279.629-.631.629-.346 0-.626-.285-.626-.629V8.108c0-.27.173-.51.43-.595.06-.023.136-.033.194-.033.195 0 .375.104.495.254l2.462 3.33V8.108c0-.345.282-.63.63-.63.345 0 .63.285.63.63v4.771zm-5.741 0c0 .344-.282.629-.631.629-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63.346 0 .628.285.628.63v4.771zm-2.466.629H4.917c-.345 0-.63-.285-.63-.629V8.108c0-.345.285-.63.63-.63.348 0 .63.285.63.63v4.141h1.756c.348 0 .629.283.629.63 0 .344-.282.629-.629.629M24 10.314C24 4.943 18.615.572 12 .572S0 4.943 0 10.314c0 4.811 4.27 8.842 10.035 9.608.391.082.923.258 1.058.59.12.301.079.766.038 1.08l-.164 1.02c-.045.301-.24 1.186 1.049.645 1.291-.539 6.916-4.078 9.436-6.975C23.176 14.393 24 12.458 24 10.314" />
    </svg>
  );
}

function MessengerLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M.001 11.639C.001 4.949 5.241 0 12.001 0S24 4.95 24 11.639c0 6.689-5.24 11.638-12 11.638-1.21 0-2.38-.16-3.47-.46a.96.96 0 00-.64.05l-2.39 1.05a.96.96 0 01-1.35-.85l-.07-2.14a.97.97 0 00-.32-.68A11.39 11.389 0 01.002 11.64zm8.32-2.19l-3.52 5.6c-.35.53.32 1.13.82.75l3.79-2.87c.26-.2.6-.2.87 0l2.8 2.1c.84.63 2.04.4 2.6-.48l3.52-5.6c.35-.53-.32-1.13-.82-.75l-3.79 2.87c-.25.2-.6.2-.86 0l-2.8-2.1a1.8 1.8 0 00-2.61.48z" />
    </svg>
  );
}

function SignalLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" fillRule="evenodd" className={className}>
      {/* Speech bubble with cutout equalizer bars */}
      <path d="M12 1.5C6.21 1.5 1.5 5.85 1.5 11.2c0 2.04.66 3.93 1.79 5.5L1.5 22.5l5.97-1.72A10.72 10.72 0 0 0 12 21.9c5.79 0 10.5-4.35 10.5-9.7S17.79 1.5 12 1.5zM8.4 9.3a.9.9 0 0 1 1.8 0v4a.9.9 0 0 1-1.8 0v-4zm2.7-1.5a.9.9 0 0 1 1.8 0v7a.9.9 0 0 1-1.8 0v-7zm2.7 1.5a.9.9 0 0 1 1.8 0v4a.9.9 0 0 1-1.8 0v-4z" />
    </svg>
  );
}

function InstagramLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M12 0C8.74 0 8.333.015 7.053.072 5.775.132 4.905.333 4.14.63c-.789.306-1.459.717-2.126 1.384S.935 3.35.63 4.14C.333 4.905.131 5.775.072 7.053.012 8.333 0 8.74 0 12s.015 3.667.072 4.947c.06 1.277.261 2.148.558 2.913.306.788.717 1.459 1.384 2.126.667.666 1.336 1.079 2.126 1.384.766.296 1.636.499 2.913.558C8.333 23.988 8.74 24 12 24s3.667-.015 4.947-.072c1.277-.06 2.148-.262 2.913-.558.788-.306 1.459-.718 2.126-1.384.666-.667 1.079-1.335 1.384-2.126.296-.765.499-1.636.558-2.913.06-1.28.072-1.687.072-4.947s-.015-3.667-.072-4.947c-.06-1.277-.262-2.149-.558-2.913-.306-.789-.718-1.459-1.384-2.126C21.319 1.347 20.651.935 19.86.63c-.765-.297-1.636-.499-2.913-.558C15.667.012 15.26 0 12 0zm0 2.16c3.203 0 3.585.016 4.85.071 1.17.055 1.805.249 2.227.415.562.217.96.477 1.382.896.419.42.679.819.896 1.381.164.422.36 1.057.413 2.227.057 1.266.07 1.646.07 4.85s-.015 3.585-.074 4.85c-.061 1.17-.256 1.805-.421 2.227-.224.562-.479.96-.899 1.382-.419.419-.824.679-1.38.896-.42.164-1.065.36-2.235.413-1.274.057-1.649.07-4.859.07-3.211 0-3.586-.015-4.859-.074-1.171-.061-1.816-.256-2.236-.421-.569-.224-.96-.479-1.379-.899-.421-.419-.69-.824-.9-1.38-.165-.42-.359-1.065-.42-2.235-.045-1.26-.061-1.649-.061-4.844 0-3.196.016-3.586.061-4.861.061-1.17.255-1.814.42-2.234.21-.57.479-.96.9-1.381.419-.419.81-.689 1.379-.898.42-.166 1.051-.361 2.221-.421 1.275-.045 1.65-.06 4.859-.06l.045.03zm0 3.678a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 1 0 0-12.324zM12 16c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm7.846-10.405a1.441 1.441 0 1 1-2.882 0 1.441 1.441 0 0 1 2.882 0z" />
    </svg>
  );
}

const LOGO_COMPONENTS: Record<string, React.ComponentType<{ className?: string }>> = {
  telegram: TelegramLogo,
  whatsapp: WhatsAppLogo,
  discord: DiscordLogo,
  slack: SlackLogo,
  teams: TeamsLogo,
  line: LineLogo,
  messenger: MessengerLogo,
  signal: SignalLogo,
  instagram: InstagramLogo,
};

export function renderChannelLogo(logoKey: string, className?: string) {
  const LogoComponent = LOGO_COMPONENTS[logoKey];
  if (LogoComponent) {
    return <LogoComponent className={className} />;
  }
  return <div className={cn("rounded bg-[var(--field-bg)]", className)} />;
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type BotInfo = { username: string; name: string };

/* ------------------------------------------------------------------ */
/*  Channel card                                                       */
/* ------------------------------------------------------------------ */

function ChannelCard({
  channel,
  connected,
  botUsername,
  onClick,
}: {
  channel: ChannelDefinition;
  connected: boolean;
  botUsername?: string;
  onClick: () => void;
}) {
  const { tl } = useAppI18n();
  const logo = renderChannelLogo(channel.logoKey, "h-6 w-6");
  const vs = connected ? "connected" as const : "disconnected" as const;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-220",
        "cursor-pointer outline-none",
        "focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]",
        "border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]",
        "hover:bg-[var(--surface-hover)]",
      )}
      aria-label={`${channel.label} — ${connected ? tl("Conectado") : tl("Desconectado")}`}
    >
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
        style={{ backgroundColor: channel.gradientFrom }}
      >
        <span style={{ color: "#ffffff" }}>{logo}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
          {channel.label}
        </div>
        <div className="mt-0.5 truncate text-xs text-[var(--text-quaternary)]">
          {connected && botUsername ? `@${botUsername}` : tl(channel.tagline)}
          {!channel.isOfficial && (
            <span className="ml-1 inline-flex items-center rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400/80">
              {tl("(não oficial)")}
            </span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center">
        <IntegrationCardStatusIndicator status={vs} />
      </div>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Channel connection area                                            */
/* ------------------------------------------------------------------ */

export function ChannelConnectionArea() {
  const { state } = useBotEditor();
  const botId = state.bot.id;

  // PRIMARY source of truth: state.bot.secrets from server component.
  // Build a per-channel connected map by checking if ALL required fields exist.
  const serverConnectedMap = useMemo(() => {
    const secrets = (state.bot.secrets ?? []) as Record<string, unknown>[];
    const secretKeys = new Set(
      secrets.map((s) => String(s.secret_key ?? "").toUpperCase()),
    );
    const result: Record<string, boolean> = {};
    for (const channel of CHANNEL_CATALOG) {
      const requiredFields = channel.fields.filter((f) => f.required);
      result[channel.key] = requiredFields.length > 0 && requiredFields.every(
        (f) => secretKeys.has(f.key.toUpperCase()),
      );
    }
    return result;
  }, [state.bot.secrets]);

  // Local override per channel: set after connecting/disconnecting in the modal
  const [localOverrideMap, setLocalOverrideMap] = useState<Record<string, boolean | null>>({});
  const [botInfoMap, setBotInfoMap] = useState<Record<string, BotInfo | null>>({});
  const [activeChannel, setActiveChannel] = useState<ChannelDefinition | null>(null);

  // Effective connected state per channel
  const getConnected = useCallback(
    (channelKey: string) => localOverrideMap[channelKey] ?? serverConnectedMap[channelKey] ?? false,
    [localOverrideMap, serverConnectedMap],
  );

  // Reset local overrides when server data catches up
  useEffect(() => {
    setLocalOverrideMap((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const key of Object.keys(next)) {
        if (next[key] !== null && serverConnectedMap[key] === next[key]) {
          next[key] = null;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [serverConnectedMap]);

  // Fetch bot info for each connected channel that has no cached info
  useEffect(() => {
    let cancelled = false;

    for (const channel of CHANNEL_CATALOG) {
      const connected = getConnected(channel.key);
      if (!connected || botInfoMap[channel.key]) continue;

      fetch(`/api/channels/${encodeURIComponent(botId)}/${channel.key}/status`, { cache: "no-store" })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (cancelled || !data) return;
          const username = data.display_id ?? data.bot_username;
          const name = data.display_name ?? data.bot_name ?? "";
          if (username) {
            setBotInfoMap((prev) => ({
              ...prev,
              [channel.key]: { username, name },
            }));
          }
        })
        .catch(() => {});
    }

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getConnected, botId]);

  const handleStatusChange = useCallback(
    (channelKey: string, newStatus: ChannelStatus, username?: string, name?: string) => {
      if (newStatus === "connected") {
        setLocalOverrideMap((prev) => ({ ...prev, [channelKey]: true }));
        if (username) {
          setBotInfoMap((prev) => ({
            ...prev,
            [channelKey]: { username, name: name ?? "" },
          }));
        }
      } else {
        setLocalOverrideMap((prev) => ({ ...prev, [channelKey]: false }));
        setBotInfoMap((prev) => ({ ...prev, [channelKey]: null }));
      }
    },
    [],
  );

  return (
    <>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {CHANNEL_CATALOG.map((channel) => (
          <ChannelCard
            key={channel.key}
            channel={channel}
            connected={getConnected(channel.key)}
            botUsername={botInfoMap[channel.key]?.username}
            onClick={() => setActiveChannel(channel)}
          />
        ))}
      </div>

      {activeChannel ? (
        <ChannelConnectionModal
          botId={botId}
          channel={activeChannel}
          status={getConnected(activeChannel.key) ? "connected" : "disconnected"}
          botInfo={botInfoMap[activeChannel.key] ?? null}
          onClose={() => setActiveChannel(null)}
          onStatusChange={(status, username, name) =>
            handleStatusChange(activeChannel.key, status, username, name)
          }
        />
      ) : null}
    </>
  );
}
