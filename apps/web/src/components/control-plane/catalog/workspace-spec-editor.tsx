"use client";

import { useEffect, useState } from "react";
import { FileText, Shield } from "lucide-react";
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
  const { tl } = useAppI18n();
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
      showToast(tl("System prompt do espaco de trabalho salvo com sucesso."), "success");
      onClose();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar o system prompt do espaco de trabalho."),
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
      title={tl("System prompt do espaco de trabalho")}
      subtitle={workspaceName}
      description={tl("Defina o contexto e as regras que devem orientar todos os times e agentes deste espaco.")}
      fieldLabel={tl("System prompt")}
      value={promptValue}
      placeholder={tl(`Ex.:
# Contexto
Produto B2B para operacoes financeiras.

# Regras
- Priorizar rastreabilidade e precisao.
- Nunca assumir dados nao confirmados.

# Qualidade esperada
Entregar respostas objetivas, com contexto suficiente para execucao segura.`)}
      onChange={setPromptValue}
      onClose={onClose}
      onSave={() => void handleSave()}
    />
  );
}

export function WorkspaceSpecIndicator({
  hasPrompt,
}: {
  hasPrompt: boolean;
}) {
  if (!hasPrompt) return null;

  return (
    <span
      className="agent-board-lane__prompt-indicator"
      title="System prompt do espaco de trabalho configurado"
    >
      <FileText size={10} />
    </span>
  );
}
