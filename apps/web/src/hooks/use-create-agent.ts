"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { isAgentIdConflict } from "@/lib/agent-id-conflict";
import { requestJson } from "@/lib/http-client";

/**
 * Creates a new agent on the backend with minimal placeholder data (default
 * name and color, status=paused) and redirects to its editor. The server
 * generates the id and the health port. The agent starts effectively as a
 * draft — it stays paused until the user publishes on the editor's
 * publication tab.
 */
export function useCreateAgent() {
  const router = useRouter();
  const { showToast } = useToast();
  const { t } = useAppI18n();
  const [creating, setCreating] = useState(false);

  const createAgent = useCallback(async () => {
    if (creating) return;
    setCreating(true);

    const displayName = t("generated.controlPlane.novo_agente_5f265c7c");

    try {
      const created = await requestJson<{ id: string }>("/api/control-plane/agents", {
        method: "POST",
        body: JSON.stringify({
          display_name: displayName,
          status: "paused",
          appearance: {
            label: displayName,
            color: "#7A8799",
            color_rgb: "122, 135, 153",
          },
          organization: { workspace_id: null, squad_id: null },
        }),
      });
      router.push(`/control-plane/agents/${created.id}`);
    } catch (err) {
      showToast(
        isAgentIdConflict(err)
          ? t("controlPlane.agent.idConflict")
          : err instanceof Error
            ? err.message
            : t("generated.controlPlane.erro_ao_criar_agente_f12f4af5"),
        "error",
      );
      setCreating(false);
    }
  }, [creating, router, showToast, t]);

  return { creating, createAgent };
}
