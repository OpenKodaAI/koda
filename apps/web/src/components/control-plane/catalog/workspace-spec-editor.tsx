"use client";

import { useEffect, useState } from "react";
import { Shield } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { requestJson } from "@/lib/http-client";
import { ScopeSystemPromptEditor } from "./scope-system-prompt-editor";

interface WorkspaceSpecEditorProps {
  workspaceId: string;
  workspaceName: string;
  open: boolean;
  onClose: () => void;
}

export function WorkspaceSpecEditor({
  workspaceId,
  workspaceName,
  open,
  onClose,
}: WorkspaceSpecEditorProps) {
  const { t } = useAppI18n();
  const { showToast } = useToast();
  const [promptValue, setPromptValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    requestJson<{ documents?: { system_prompt_md?: string } }>(
      `/api/control-plane/workspaces/${workspaceId}/spec`,
    )
      .then((data) => {
        setPromptValue(String(data.documents?.system_prompt_md || ""));
      })
      .catch(() => {
        setPromptValue("");
      })
      .finally(() => setLoading(false));
  }, [open, workspaceId]);

  async function handleSave() {
    setSaving(true);
    try {
      await requestJson(`/api/control-plane/workspaces/${workspaceId}/spec`, {
        method: "PUT",
        body: JSON.stringify({
          spec: {},
          documents: {
            system_prompt_md: promptValue,
          },
        }),
      });
      showToast(t("generated.controlPlane.system_prompt_do_espaco_de_trabalho_salvo_co_1c8c5a96"), "success");
      onClose();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : t("generated.controlPlane.erro_ao_salvar_o_system_prompt_do_espaco_de__efb39d2d"),
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
      icon={<Shield size={18} />}
      title={t("generated.controlPlane.system_prompt_do_espaco_de_trabalho_c13ea4d3")}
      subtitle={workspaceName}
      description={t("generated.controlPlane.defina_o_contexto_e_as_regras_que_devem_orie_d6280bca")}
      fieldLabel={t("generated.controlPlane.system_prompt_0bbdbb67")}
      value={promptValue}
      placeholder={t("generated.controlPlane.ex_contexto_produto_b2b_para_operacoes_finan_a47669c6")}
      onChange={setPromptValue}
      onClose={onClose}
      onSave={() => void handleSave()}
    />
  );
}
