"use client";

import { Sparkles, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";
import type { Mention } from "@/lib/contracts/sessions";

export interface TrackedMention {
  kind: Mention["kind"];
  slug: string;
  label: string;
}

interface ComposerMentionBadgesProps {
  mentions: TrackedMention[];
  onRemove: (mention: TrackedMention) => void;
}

export function ComposerMentionBadges({ mentions, onRemove }: ComposerMentionBadgesProps) {
  const { t } = useAppI18n();
  if (mentions.length === 0) return null;

  return (
    <div className="composer-mention-row">
      {mentions.map((mention) => {
        const isMcp = mention.kind === "mcp";
        return (
          <span
            key={`${mention.kind}:${mention.slug}`}
            className="composer-mention-badge"
            data-mention-kind={mention.kind}
            data-mention-slug={mention.slug}
          >
            <span className="composer-mention-badge__logo" aria-hidden>
              {isMcp ? (
                renderIntegrationLogo(mention.slug, "composer-mention-badge__logo-art")
              ) : (
                <Sparkles
                  className="composer-mention-badge__logo-art"
                  strokeWidth={1.75}
                  style={{ color: "var(--text-tertiary)" }}
                />
              )}
            </span>
            <span className="composer-mention-badge__label">{mention.label}</span>
            <button
              type="button"
              onClick={() => onRemove(mention)}
              aria-label={t("chat.composer.mention.remove", { label: mention.label })}
              className="composer-mention-badge__remove"
            >
              <X className="composer-mention-badge__x" strokeWidth={2} aria-hidden />
            </button>
          </span>
        );
      })}
    </div>
  );
}
