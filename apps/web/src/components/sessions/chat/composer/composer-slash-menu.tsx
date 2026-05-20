"use client";

import { useMemo } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useCommandsCatalog } from "@/hooks/use-commands-catalog";
import {
  ComposerSuggestionList,
  type SuggestionGroup,
  type SuggestionItem,
} from "@/components/sessions/chat/composer/composer-suggestion-list";
import type { ChatCommand } from "@/lib/contracts/chat-commands";

export interface ComposerSlashMenuContentProps {
  query: string;
  onQueryChange?: (next: string) => void;
  agentId?: string | null;
  activeIndex: number;
  onItemsChange: (items: ChatCommand[]) => void;
  onActiveIndex: (index: number) => void;
  onSelect: (command: ChatCommand) => void;
  listboxId: string;
  idPrefix: string;
}

function commandToSuggestionItem(command: ChatCommand): SuggestionItem {
  return {
    id: command.id,
    label: command.label,
    description: command.description,
    meta: null,
  };
}

export function ComposerSlashMenuContent({
  query,
  onQueryChange,
  agentId,
  activeIndex,
  onItemsChange,
  onActiveIndex,
  onSelect,
  listboxId,
  idPrefix,
}: ComposerSlashMenuContentProps) {
  const { t } = useAppI18n();
  const { filtered } = useCommandsCatalog({ query, agentId });

  // Memoize the items array reference so a stable identity flows up to the
  // orchestrator. onItemsChange() is invoked every time the filtered output
  // changes so the keyboard handler can pick the right command on Enter.
  useMemo(() => {
    onItemsChange(filtered);
    return filtered;
  }, [filtered, onItemsChange]);

  const groups: SuggestionGroup[] = [
    {
      id: "commands",
      label: null,
      items: filtered.map(commandToSuggestionItem),
    },
  ];

  return (
    <ComposerSuggestionList
      groups={groups}
      activeIndex={activeIndex}
      onSelect={(item) => {
        const command = filtered.find((c) => c.id === item.id);
        if (command) onSelect(command);
      }}
      onHover={onActiveIndex}
      emptyLabel={t("chat.composer.suggestions.empty", undefined)}
      ariaLabel={t("chat.composer.suggestions.commands", undefined)}
      idPrefix={idPrefix}
      listboxId={listboxId}
      searchValue={query}
      onSearchChange={onQueryChange}
      searchPlaceholder={t("chat.composer.suggestions.searchCommands", undefined)}
    />
  );
}
