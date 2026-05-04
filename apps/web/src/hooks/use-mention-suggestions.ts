"use client";

import { useMemo } from "react";
import { useSkillsCatalog } from "@/hooks/use-command-catalog";
import { useMcpCatalogSuggestions } from "@/hooks/use-mcp-catalog-suggestions";
import type { Mention } from "@/lib/contracts/sessions";

export interface MentionCandidate {
  kind: Mention["kind"];
  slug: string;
  label: string;
  description: string | null;
  /** Hex color for swatch (skill colours, MCP brand). */
  color: string | null;
  /** Logo URL when available (MCPs); null for skills (we use a swatch). */
  iconUrl: string | null;
}

const MAX_PER_GROUP = 8;

function normalize(value: string): string {
  return value.toLowerCase().trim();
}

function matchesQuery(haystack: string | null | undefined, query: string): boolean {
  if (!query) return true;
  if (!haystack) return false;
  return normalize(haystack).includes(normalize(query));
}

/**
 * Coalesces the skills catalog and MCP catalog into a single shape suitable
 * for the mention menu. Filters by `query` (substring on slug / label /
 * description) and caps each group at 8 items.
 */
export function useMentionSuggestions(
  query: string,
  agentId: string | null | undefined,
): {
  skills: MentionCandidate[];
  mcps: MentionCandidate[];
  isLoading: boolean;
} {
  const skillEntries = useSkillsCatalog(agentId);
  const { servers, isLoading: mcpLoading } = useMcpCatalogSuggestions();

  const skills: MentionCandidate[] = useMemo(() => {
    return skillEntries
      .filter((entry) => {
        return (
          matchesQuery(entry.id, query) ||
          matchesQuery(entry.title, query) ||
          matchesQuery(entry.description ?? null, query)
        );
      })
      .slice(0, MAX_PER_GROUP)
      .map((entry) => ({
        kind: "skill" as const,
        slug: entry.id,
        label: entry.title,
        description: entry.description ?? null,
        color: null,
        iconUrl: null,
      }));
  }, [query, skillEntries]);

  const mcps: MentionCandidate[] = useMemo(() => {
    return servers
      .filter((server) => {
        return (
          matchesQuery(server.server_key, query) ||
          matchesQuery(server.display_name, query) ||
          matchesQuery(server.tagline, query)
        );
      })
      .slice(0, MAX_PER_GROUP)
      .map((server) => ({
        kind: "mcp" as const,
        slug: server.server_key,
        label: server.display_name,
        description: server.tagline || null,
        color: null,
        iconUrl: server.logo_key ?? null,
      }));
  }, [query, servers]);

  return { skills, mcps, isLoading: mcpLoading };
}
