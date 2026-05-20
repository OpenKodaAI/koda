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
import { AsyncActionButton, InlineSpinner } from "@/components/ui/async-feedback";
import { InlineAlert } from "@/components/ui/inline-alert";
import { StatusDot } from "@/components/ui/status-dot";
import { getAgentLifecycleState } from "@/lib/agent-lifecycle";
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
  const { t, tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const agentId = state.agent.id;
  const dirtyKeys = Object.entries(state.dirty)
    .filter(([, flag]) => Boolean(flag))
    .map(([key]) => key);
  const hasPendingChanges = dirtyKeys.length > 0;

  const lifecycle = getAgentLifecycleState({
    status: state.agent.status,
    appliedVersion: state.agent.applied_version ?? null,
    desiredVersion: state.agent.desired_version ?? null,
    hasPendingChanges,
  });

  async function handleClone() {
    if (!state.cloneDisplayName.trim()) {
      showToast(t("generated.controlPlane.nome_do_clone_e_obrigatorio_350c2e21"), "warning");
      return;
    }
    const cloneId =
      state.cloneDisplayName
        .trim()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
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
        successMessage: t("generated.controlPlane.bot_clonado_com_sucesso_0862a4f1"),
        errorMessage: t("generated.controlPlane.erro_ao_clonar_60fe99e8"),
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
        successMessage: t("generated.controlPlane.bot_removido_aff4af6d"),
        errorMessage: t("generated.controlPlane.erro_ao_remover_bot_5cd215a5"),
      },
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4">
        <span className="eyebrow">{t("generated.controlPlane.status_do_agente_e4db87fa")}</span>

        <div className="flex flex-col gap-1.5">
          <span className="inline-flex items-center gap-2">
            <StatusDot tone={lifecycle.tone} pulse={lifecycle.pulse} />
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {t(lifecycle.labelKey, lifecycle.descriptionOptions)}
            </span>
          </span>
          <p className="max-w-xl text-xs leading-relaxed text-[var(--text-tertiary)]">
            {t(lifecycle.descriptionKey, lifecycle.descriptionOptions)}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-[var(--text-tertiary)]">
          <span className="inline-flex items-center gap-1.5">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.versao_aplicada_ffebc9f4")}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">
              {state.agent.applied_version ?? "—"}
            </span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="text-[var(--text-quaternary)]">{t("generated.controlPlane.versao_desejada_3db461e6")}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">
              {state.agent.desired_version ?? t("generated.controlPlane.rascunho_1e888028")}
            </span>
          </span>
        </div>

        {hasPendingChanges ? (
          <InlineAlert tone="warning">
            <span className="text-[var(--text-secondary)]">
              {t("generated.controlPlane.alteracoes_pendentes_em_0ababa4f")}: {" "}
              {dirtyKeys
                .map((key) => tl(SECTION_LABELS[key] ?? key))
                .join(" · ")}
            </span>
          </InlineAlert>
        ) : null}
      </section>

      <div className="border-t border-[color:var(--divider-hair)]" />

      <PolicyCard
        title={t("generated.controlPlane.clonar_agente_56a117f8")}
        description={t("generated.controlPlane.cria_uma_copia_com_configuracao_identica_eb5d12fb")}
        icon={Copy}
        variant="flat"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <FormInput
              label={t("generated.controlPlane.nome_do_clone_338024be")}
              value={state.cloneDisplayName}
              onChange={(e) => updateField("cloneDisplayName", e.target.value)}
              placeholder={t("generated.controlPlane.copia_de_8d4e6578")}
            />
          </div>
          <AsyncActionButton
            type="button"
            variant="secondary"
            size="sm"
            disabled={!state.cloneDisplayName.trim()}
            loading={isPending("clone")}
            loadingLabel={t("generated.controlPlane.clonando_adac72ae")}
            onClick={handleClone}
          >
            {t("generated.controlPlane.clonar_23373a96")}
          </AsyncActionButton>
        </div>
      </PolicyCard>

      <div className="border-t border-[color:var(--divider-hair)]" />

      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-quaternary)]">
          {t("generated.controlPlane.remove_este_agente_e_todos_os_dados_associad_0b087473")}
        </span>
        <button
          type="button"
          onClick={() => setShowDeleteDialog(true)}
          disabled={isPending("delete")}
          aria-label={isPending("delete") ? t("generated.controlPlane.removendo_ba1bef53") : undefined}
          aria-busy={isPending("delete") || undefined}
          className="inline-flex min-h-5 min-w-24 items-center justify-center text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--tone-danger-text)] disabled:opacity-50"
        >
          {isPending("delete") ? (
            <InlineSpinner className="h-3.5 w-3.5" />
          ) : (
            t("generated.controlPlane.remover_agente_952bb8b7")
          )}
        </button>
      </div>

      <ConfirmationDialog
        open={showDeleteDialog}
        title={t("generated.controlPlane.remover_agente_952bb8b7")}
        message={t(
          "generated.controlPlane.tem_certeza_que_deseja_remover_name_todas_as_5e365cce",
          { name: state.displayName || agentId },
        )}
        confirmLabel={t("generated.controlPlane.remover_5465770e")}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteDialog(false)}
      />
    </div>
  );
}
