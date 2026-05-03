"use client";

import { Sparkles, X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Badge } from "@/components/ui/badge";
import {
  getIntegrationAccent,
  getIntegrationLogo,
} from "@/components/control-plane/system/integrations/integration-logos";
import type { Mention } from "@/lib/contracts/sessions";

export interface ComposerMentionBadge {
  kind: Mention["kind"];
  slug: string;
  /** Human-readable label resolved from the catalog at insertion time. */
  label: string;
  /** True when the slug isn't recognised by the current catalog (e.g. pasted token). */
  unresolved?: boolean;
}

export interface ComposerMentionBadgesProps {
  mentions: ComposerMentionBadge[];
  onRemove: (mention: ComposerMentionBadge) => void;
}

const MAX_VISIBLE = 12;

/** Skills don't carry a brand colour — use the canonical Koda accent so the
 * row reads as a single family while still distinguishing them from MCPs. */
const SKILL_ACCENT = { from: "var(--accent)", to: "var(--accent-hover)" } as const;

export function ComposerMentionBadges({
  mentions,
  onRemove,
}: ComposerMentionBadgesProps) {
  const { t } = useAppI18n();

  if (mentions.length === 0) return null;
  const visible = mentions.slice(0, MAX_VISIBLE);
  const overflow = mentions.length - visible.length;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 pt-2 pb-1 max-h-16 overflow-y-auto">
      {visible.map((mention) => {
        const Logo =
          mention.kind === "mcp" && !mention.unresolved
            ? getIntegrationLogo(mention.slug)
            : null;
        const accent =
          mention.kind === "mcp" && !mention.unresolved
            ? getIntegrationAccent(mention.slug)
            : SKILL_ACCENT;
        const tinted = !mention.unresolved
          ? {
              borderColor:
                mention.kind === "mcp" ? `${accent.from}66` : "var(--border-subtle)",
              background:
                mention.kind === "mcp" ? `${accent.from}1a` : "var(--panel-soft)",
            }
          : undefined;

        return (
          <Badge
            key={`${mention.kind}:${mention.slug}`}
            variant={mention.unresolved ? "warning" : "outline"}
            size="sm"
            className="inline-flex items-center gap-1.5 pl-1.5 pr-1"
            style={tinted}
          >
            {Logo ? (
              <Logo className="h-3 w-3 shrink-0" />
            ) : (
              <Sparkles
                className="icon-xs shrink-0"
                strokeWidth={1.75}
                aria-hidden
                style={
                  mention.kind === "skill" && !mention.unresolved
                    ? { color: "var(--accent)" }
                    : undefined
                }
              />
            )}
            <span className="truncate max-w-[160px]">{mention.label}</span>
            <button
              type="button"
              onClick={() => onRemove(mention)}
              aria-label={t("chat.composer.mention.remove", {
                defaultValue: "Remove {{label}}",
                label: mention.label,
              })}
              className="inline-flex h-4 w-4 items-center justify-center rounded-full hover:bg-[var(--hover-tint)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X className="icon-xs" strokeWidth={1.75} aria-hidden />
            </button>
          </Badge>
        );
      })}
      {overflow > 0 ? (
        <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
          +{overflow}
        </span>
      ) : null}
    </div>
  );
}
