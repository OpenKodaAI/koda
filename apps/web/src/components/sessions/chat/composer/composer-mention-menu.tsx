"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
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
  onQueryChange?: (next: string) => void;
  agentId?: string | null;
  activeIndex: number;
  onItemsChange: (items: MentionCandidate[]) => void;
  onActiveIndex: (index: number) => void;
  onSelect: (candidate: MentionCandidate) => void;
  listboxId: string;
  idPrefix: string;
}

const MCP_PAGE_SIZE = 10;
const PAGE_REVEAL_DELAY_MS = 220;

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
    meta: null,
  };
}

export function ComposerMentionMenuContent({
  query,
  onQueryChange,
  agentId,
  activeIndex,
  onItemsChange,
  onActiveIndex,
  onSelect,
  listboxId,
  idPrefix,
}: ComposerMentionMenuContentProps) {
  const { t } = useAppI18n();
  const { skills, mcps, isLoading } = useMentionSuggestions(query, agentId);

  const [mcpVisible, setMcpVisible] = useState(MCP_PAGE_SIZE);
  const [paging, setPaging] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const pageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset pagination + cancel any pending reveal whenever the search query
  // (or the underlying mcp dataset) changes — otherwise the second page would
  // briefly leak into the next filtered set.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMcpVisible(MCP_PAGE_SIZE);
    setPaging(false);
    if (pageTimerRef.current) {
      clearTimeout(pageTimerRef.current);
      pageTimerRef.current = null;
    }
  }, [query, mcps.length]);

  useEffect(() => {
    return () => {
      if (pageTimerRef.current) {
        clearTimeout(pageTimerRef.current);
        pageTimerRef.current = null;
      }
    };
  }, []);

  const visibleMcps = useMemo(() => mcps.slice(0, mcpVisible), [mcps, mcpVisible]);
  const hasMoreMcps = mcpVisible < mcps.length;

  const flat = useMemo<MentionCandidate[]>(
    () => [...skills, ...visibleMcps],
    [skills, visibleMcps],
  );

  useEffect(() => {
    onItemsChange(flat);
  }, [flat, onItemsChange]);

  const loadMore = useCallback(() => {
    if (!hasMoreMcps || paging) return;
    setPaging(true);
    pageTimerRef.current = setTimeout(() => {
      setMcpVisible((current) => Math.min(current + MCP_PAGE_SIZE, mcps.length));
      setPaging(false);
      pageTimerRef.current = null;
    }, PAGE_REVEAL_DELAY_MS);
  }, [hasMoreMcps, mcps.length, paging]);

  // IntersectionObserver triggers loadMore when the sentinel scrolls into the
  // visible portion of the listbox. This gives the "infinite scroll" feel
  // without a manual button.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMoreMcps) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadMore();
        }
      },
      { root: null, threshold: 0.1 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMoreMcps, loadMore]);

  const groups: SuggestionGroup[] = [
    {
      id: "all",
      label: null,
      items: flat.map(candidateToItem),
    },
  ];

  const showInitialLoader = isLoading && skills.length === 0 && mcps.length === 0;
  const showFooterLoader = paging || hasMoreMcps;

  const loaderShell = "flex items-center justify-center gap-1.5 px-3 py-2.5 min-h-[2rem] text-[0.75rem] text-[var(--text-tertiary)]";
  const spinnerClass = "h-3.5 w-3.5 shrink-0 animate-spin";

  const footer = showInitialLoader ? (
    <div
      className={loaderShell}
      role="status"
      aria-live="polite"
      aria-label={t("chat.composer.suggestions.loading", { defaultValue: "Loading…" })}
    >
      <Loader2 className={spinnerClass} strokeWidth={2} aria-hidden />
    </div>
  ) : showFooterLoader ? (
    <div
      ref={sentinelRef}
      className={loaderShell}
      role="status"
      aria-live="polite"
      data-paging={paging ? "true" : "false"}
    >
      <Loader2 className={spinnerClass} strokeWidth={2} aria-hidden />
    </div>
  ) : null;

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
      searchValue={query}
      onSearchChange={onQueryChange}
      searchPlaceholder={t("chat.composer.suggestions.searchMentions", {
        defaultValue: "Search integrations and skills…",
      })}
      footer={footer}
    />
  );
}
