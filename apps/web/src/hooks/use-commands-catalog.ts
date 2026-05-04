"use client";

import { useMemo } from "react";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import {
  STATIC_COMMAND_FALLBACK,
  chatCommandsCatalogSchema,
  type ChatCommand,
} from "@/lib/contracts/chat-commands";

async function fetchCommandsCatalog(): Promise<ChatCommand[]> {
  try {
    const response = await fetch("/api/control-plane/commands/list", {
      method: "GET",
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) return STATIC_COMMAND_FALLBACK;
    const body = (await response.json().catch(() => null)) as unknown;
    const parsed = chatCommandsCatalogSchema.safeParse(body);
    if (!parsed.success) return STATIC_COMMAND_FALLBACK;
    // Always merge fallback so core commands are reachable even if backend
    // forgot to publish them.
    const seen = new Set(parsed.data.items.map((cmd) => cmd.id));
    const merged = [...parsed.data.items];
    for (const fallback of STATIC_COMMAND_FALLBACK) {
      if (!seen.has(fallback.id)) merged.push(fallback);
    }
    return merged;
  } catch {
    return STATIC_COMMAND_FALLBACK;
  }
}

export interface UseCommandsCatalogResult {
  commands: ChatCommand[];
  filtered: ChatCommand[];
  isLoading: boolean;
}

function normalize(value: string): string {
  return value.toLowerCase().trim();
}

function matches(command: ChatCommand, query: string): boolean {
  if (!query) return true;
  const q = normalize(query);
  if (normalize(command.id).includes(q)) return true;
  if (normalize(command.label).includes(q)) return true;
  if (normalize(command.description).includes(q)) return true;
  if (command.keywords?.some((keyword) => normalize(keyword).includes(q))) {
    return true;
  }
  return false;
}

/**
 * Fetches the slash-command catalog with a static fallback. Filters the
 * catalog by the active query (matched against id/label/description/keywords)
 * and optionally by the active agent id.
 *
 * The merged result preserves backend ordering and appends fallback commands
 * not present in the backend catalog so the user always has access to the
 * core commands.
 */
export function useCommandsCatalog(options: {
  query?: string;
  agentId?: string | null;
  enabled?: boolean;
} = {}): UseCommandsCatalogResult {
  const { query = "", agentId, enabled = true } = options;

  const fetched = useControlPlaneQuery<ChatCommand[]>({
    tier: "catalog",
    queryKey: ["chat", "commands", "list"],
    enabled,
    queryFn: fetchCommandsCatalog,
    staleTime: 60_000,
    notifyOnChangeProps: ["data"],
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  const commands = fetched.data ?? STATIC_COMMAND_FALLBACK;

  const filtered = useMemo(() => {
    return commands.filter((command) => {
      if (
        agentId &&
        command.agent_scope &&
        command.agent_scope.length > 0 &&
        !command.agent_scope.includes(agentId)
      ) {
        return false;
      }
      return matches(command, query);
    });
  }, [agentId, commands, query]);

  return {
    commands,
    filtered,
    isLoading: fetched.isLoading,
  };
}
