"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Copy } from "lucide-react";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useToast } from "@/hooks/use-toast";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { FormInput } from "@/components/control-plane/shared/form-field";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { InlineAlert } from "@/components/ui/inline-alert";
import { StatusDot } from "@/components/ui/status-dot";
import { requestJson } from "@/lib/http-client";

const SECTION_LABELS: Record<string, string> = {
  meta: "Identidade e metadados",
  documents: "Documentos e instruções",
  agentSpec: "Especificação do agente",
  sections: "Seções de configuração",
  collections: "Coleções de conhecimento",
};

export function TabPublicacao() {
  const { state, updateField } = useAgentEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const agentId = state.agent.id;
  const dirtyKeys = Object.entries(state.dirty)
    .filter(([, flag]) => Boolean(flag))
    .map(([key]) => key);
  const hasPendingChanges = dirtyKeys.length > 0;

  async function handleClone() {
    if (!state.cloneDisplayName.trim()) {
      showToast(tl("Nome do clone e obrigatorio."), "warning");
      return;
    }
    const cloneId =
      state.cloneDisplayName
        .trim()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9_\s-]/g, "")
        .replace(/[\s-]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 80) + `-${Date.now().toString(36)}`;
    await runAction(
      "clone",
      async () => {
        await requestJson(`/api/control-plane/agents/${agentId}/clone`, {
          method: "POST",
          body: JSON.stringify({
            id: cloneId,
            display_name: state.cloneDisplayName.trim(),
          }),
        });
        router.push(`/control-plane/agents/${cloneId}`);
      },
      {
        successMessage: tl("Bot clonado com sucesso."),
        errorMessage: tl("Erro ao clonar."),
      },
    );
  }

  async function handleDelete() {
    setShowDeleteDialog(false);
    await runAction(
      "delete",
      async () => {
        await requestJson(`/api/control-plane/agents/${agentId}`, {
          method: "DELETE",
        });
        router.push("/control-plane");
      },
      {
        successMessage: tl("Bot removido."),
        errorMessage: tl("Erro ao remover bot."),
      },
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4">
        <span className="eyebrow">{tl("Resumo de alteracoes")}</span>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="inline-flex items-center gap-2">
            <StatusDot
              tone={hasPendingChanges ? "warning" : "success"}
              pulse={hasPendingChanges}
            />
            <span className="text-[var(--text-primary)]">
              {hasPendingChanges
                ? tl("Alteracoes pendentes")
                : tl("Publicado")}
            </span>
          </span>
          <span className="inline-flex items-center gap-1.5 text-[var(--text-tertiary)]">
            <span className="text-[var(--text-quaternary)]">{tl("Versao publicada")}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">
              {state.agent.applied_version || "—"}
            </span>
          </span>
          <span className="inline-flex items-center gap-1.5 text-[var(--text-tertiary)]">
            <span className="text-[var(--text-quaternary)]">{tl("Versao desejada")}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">
              {state.agent.desired_version || tl("Rascunho")}
            </span>
          </span>
        </div>

        {hasPendingChanges ? (
          <InlineAlert tone="warning">
            <span className="text-[var(--text-secondary)]">
              {dirtyKeys
                .map((key) => tl(SECTION_LABELS[key] ?? key))
                .join(" · ")}
            </span>
          </InlineAlert>
        ) : null}
      </section>

      <div className="border-t border-[color:var(--divider-hair)]" />

      <PolicyCard
        title={tl("Clonar agente")}
        description={tl("Cria uma copia com configuracao identica.")}
        icon={Copy}
        variant="flat"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <FormInput
              label={tl("Nome do clone")}
              value={state.cloneDisplayName}
              onChange={(e) => updateField("cloneDisplayName", e.target.value)}
              placeholder={tl("Copia de...")}
            />
          </div>
          <AsyncActionButton
            type="button"
            variant="secondary"
            size="sm"
            disabled={!state.cloneDisplayName.trim()}
            loading={isPending("clone")}
            loadingLabel={tl("Clonando")}
            onClick={handleClone}
          >
            {tl("Clonar")}
          </AsyncActionButton>
        </div>
      </PolicyCard>

      <div className="border-t border-[color:var(--divider-hair)]" />

      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-quaternary)]">
          {tl("Remove este agente e todos os dados associados.")}
        </span>
        <button
          type="button"
          onClick={() => setShowDeleteDialog(true)}
          disabled={isPending("delete")}
          className="text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--tone-danger-text)] disabled:opacity-50"
        >
          {isPending("delete") ? tl("Removendo...") : tl("Remover agente")}
        </button>
      </div>

      <ConfirmationDialog
        open={showDeleteDialog}
        title={tl("Remover agente")}
        message={tl(
          'Tem certeza que deseja remover "{{name}}"? Todas as configuracoes, documentos e versoes serao permanentemente excluidos. Esta acao nao pode ser desfeita.',
          { name: state.displayName || agentId },
        )}
        confirmLabel={tl("Remover")}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteDialog(false)}
      />
    </div>
  );
}
