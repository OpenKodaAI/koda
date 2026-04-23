"use client";

import { useEffect, useState } from "react";
import { FileText, Users } from "lucide-react";
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
  const { tl } = useAppI18n();
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
      showToast(tl("System prompt do time salvo com sucesso."), "success");
      onClose();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar o system prompt do time."),
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
      title={tl("System prompt do time")}
      subtitle={squadName}
      description={tl("Defina o contexto, os acordos de execucao e o conhecimento que devem orientar os agentes deste time.")}
      fieldLabel={tl("System prompt")}
      value={promptValue}
      placeholder={tl(`Ex.:
# Missao do time
Garantir entregas de plataforma com confiabilidade e baixo risco.

# Forma de atuar
- Quebrar tarefas em etapas verificaveis.
- Explicitar riscos e rollback sempre que houver mudancas sensiveis.

# Conhecimento util
Preferimos solucoes simples, reversiveis e com boa observabilidade.`)}
      onChange={setPromptValue}
      onClose={onClose}
      onSave={() => void handleSave()}
    />
  );
}

export function SquadSpecIndicator({
  hasPrompt,
}: {
  hasPrompt: boolean;
}) {
  if (!hasPrompt) return null;

  return (
    <span
      className="agent-board-lane__prompt-indicator"
      title="System prompt do time configurado"
    >
      <FileText size={10} />
    </span>
  );
}
