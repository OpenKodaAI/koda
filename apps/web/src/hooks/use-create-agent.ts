"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";

async function postJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "error" in payload
        ? String((payload as { error: unknown }).error)
        : `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

/**
 * Creates a new agent on the backend with minimal placeholder data (random id,
 * default color, status=paused) and redirects to its editor. The agent starts
 * effectively as a draft — it stays paused until the user publishes on the
 * editor's publication tab.
 */
export function useCreateAgent() {
  const router = useRouter();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [creating, setCreating] = useState(false);

  const createAgent = useCallback(async () => {
    if (creating) return;
    setCreating(true);

    const existingIds = new Set(agents.map((agent) => agent.id));
    let agentId = `AGENT_${Date.now().toString(36).toUpperCase()}`;
    let attempt = 0;
    while (existingIds.has(agentId) && attempt < 5) {
      agentId = `AGENT_${Date.now().toString(36).toUpperCase()}_${attempt}`;
      attempt += 1;
    }

    const ports = agents
      .map((agent) => Number((agent as { runtime_endpoint?: { health_port?: number } }).runtime_endpoint?.health_port ?? 0))
      .filter((value) => Number.isInteger(value) && value > 0);
    const healthPort = Math.max(8079, ...ports) + 1;
    const displayName = tl("Novo agente");

    try {
      await postJson("/api/control-plane/agents", {
        method: "POST",
        body: JSON.stringify({
          id: agentId,
          display_name: displayName,
          status: "paused",
          storage_namespace: agentId.toLowerCase(),
          appearance: {
            label: displayName,
            color: "#7A8799",
            color_rgb: "122, 135, 153",
          },
          runtime_endpoint: {
            health_port: healthPort,
            health_url: `http://127.0.0.1:${healthPort}/health`,
            runtime_base_url: `http://127.0.0.1:${healthPort}`,
          },
          organization: { workspace_id: null, squad_id: null },
        }),
      });
      router.push(`/control-plane/agents/${agentId}`);
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao criar agente."),
        "error",
      );
      setCreating(false);
    }
  }, [agents, creating, router, showToast, tl]);

  return { creating, createAgent };
}
