"use client";

import { useEffect, useState } from "react";
import { Users } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { requestJson } from "@/lib/http-client";
import { ScopeSystemPromptEditor } from "./scope-system-prompt-editor";

interface SquadSpecEditorProps {
  workspaceId: string;
  squadId: string;
  squadName: string;
  open: boolean;
  onClose: () => void;
}

export function SquadSpecEditor({
  workspaceId,
  squadId,
  squadName,
  open,
  onClose,
}: SquadSpecEditorProps) {
  const { t } = useAppI18n();
  const { showToast } = useToast();
  const [promptValue, setPromptValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    requestJson<{ documents?: { system_prompt_md?: string } }>(
      `/api/control-plane/workspaces/${workspaceId}/squads/${squadId}/spec`,
    )
      .then((data) => {
        setPromptValue(String(data.documents?.system_prompt_md || ""));
      })
      .catch(() => {
        setPromptValue("");
      })
      .finally(() => setLoading(false));
  }, [open, workspaceId, squadId]);

  async function handleSave() {
    setSaving(true);
    try {
      await requestJson(`/api/control-plane/workspaces/${workspaceId}/squads/${squadId}/spec`, {
        method: "PUT",
        body: JSON.stringify({
          spec: {},
          documents: {
            system_prompt_md: promptValue,
          },
        }),
      });
      showToast(t("generated.controlPlane.system_prompt_do_time_salvo_com_sucesso_4532fabe"), "success");
      onClose();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : t("generated.controlPlane.erro_ao_salvar_o_system_prompt_do_time_0a6d5a62"),
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScopeSystemPromptEditor
      open={open}
      loading={loading}
      saving={saving}
      icon={<Users size={18} />}
      title={t("generated.controlPlane.system_prompt_do_time_4067e288")}
      subtitle={squadName}
      description={t("generated.controlPlane.defina_o_contexto_os_acordos_de_execucao_e_o_7184ccd1")}
      fieldLabel={t("generated.controlPlane.system_prompt_0bbdbb67")}
      value={promptValue}
      placeholder={t("generated.controlPlane.ex_missao_do_time_garantir_entregas_de_plata_4a3381c8")}
      onChange={setPromptValue}
      onClose={onClose}
      onSave={() => void handleSave()}
    />
  );
}
