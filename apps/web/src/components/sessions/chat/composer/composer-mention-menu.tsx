"use client";

import { useEffect, useMemo } from "react";
import { Sparkles } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  getIntegrationAccent,
  getIntegrationLogo,
} from "@/components/control-plane/system/integrations/integration-logos";
import {
  useMentionSuggestions,
  type MentionCandidate,
} from "@/hooks/use-mention-suggestions";
import {
  ComposerSuggestionList,
  type SuggestionGroup,
  type SuggestionItem,
} from "@/components/sessions/chat/composer/composer-suggestion-list";

export interface ComposerMentionMenuContentProps {
  query: string;
  agentId?: string | null;
  activeIndex: number;
  onItemsChange: (items: MentionCandidate[]) => void;
  onActiveIndex: (index: number) => void;
  onSelect: (candidate: MentionCandidate) => void;
  listboxId: string;
  idPrefix: string;
}

function candidateToItem(candidate: MentionCandidate): SuggestionItem {
  let iconNode;
  let swatchColor: string | null = null;

  if (candidate.kind === "mcp") {
    const Logo = getIntegrationLogo(candidate.slug);
    const accent = getIntegrationAccent(candidate.slug);
    iconNode = Logo ? (
      <Logo className="h-3.5 w-3.5" />
    ) : null;
    swatchColor = accent.from;
  } else {
    iconNode = (
      <Sparkles
        className="icon-xs"
        strokeWidth={1.75}
        aria-hidden
        style={{ color: "var(--accent)" }}
      />
    );
  }

  return {
    id: `${candidate.kind}:${candidate.slug}`,
    label: candidate.label,
    description: candidate.description,
    swatchColor,
    iconNode,
    meta: candidate.kind === "skill" ? "skill" : "mcp",
  };
}

export function ComposerMentionMenuContent({
  query,
  agentId,
  activeIndex,
  onItemsChange,
  onActiveIndex,
  onSelect,
  listboxId,
  idPrefix,
}: ComposerMentionMenuContentProps) {
  const { t } = useAppI18n();
  const { skills, mcps } = useMentionSuggestions(query, agentId);

  const flat = useMemo(() => [...skills, ...mcps], [mcps, skills]);

  useEffect(() => {
    onItemsChange(flat);
  }, [flat, onItemsChange]);

  const groups: SuggestionGroup[] = [
    {
      id: "skills",
      label: t("chat.composer.suggestions.skills", { defaultValue: "Skills" }),
      items: skills.map(candidateToItem),
    },
    {
      id: "mcp",
      label: t("chat.composer.suggestions.mcp", { defaultValue: "MCP servers" }),
      items: mcps.map(candidateToItem),
    },
  ];

  return (
    <ComposerSuggestionList
      groups={groups}
      activeIndex={activeIndex}
      onSelect={(item) => {
        const candidate = flat.find((c) => `${c.kind}:${c.slug}` === item.id);
        if (candidate) onSelect(candidate);
      }}
      onHover={onActiveIndex}
      emptyLabel={t("chat.composer.suggestions.empty", { defaultValue: "No matches" })}
      ariaLabel={t("chat.composer.suggestions.mentionList", {
        defaultValue: "Skills and MCP servers",
      })}
      idPrefix={idPrefix}
      listboxId={listboxId}
    />
  );
}
