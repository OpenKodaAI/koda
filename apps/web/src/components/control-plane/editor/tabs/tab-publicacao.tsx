"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Copy } from "lucide-react";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useToast } from "@/hooks/use-toast";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { FormInput } from "@/components/control-plane/shared/form-field";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { requestJson } from "@/lib/http-client";

/* -------------------------------------------------------------------------- */
/*  Publication badge                                                          */
/* -------------------------------------------------------------------------- */

function PublicationBadge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  const toneClass =
    tone === "success"
      ? "border-[var(--tone-success-border)] bg-[rgba(77,137,100,0.08)] text-[var(--tone-success-text)]"
      : tone === "warning"
        ? "border-[var(--tone-warning-border)] bg-[rgba(184,137,56,0.08)] text-[var(--tone-warning-text)]"
        : tone === "danger"
          ? "border-[var(--tone-danger-border)] bg-[rgba(180,90,105,0.08)] text-[var(--tone-danger-text)]"
          : tone === "info"
            ? "border-[var(--tone-info-border)] bg-[rgba(76,127,209,0.08)] text-[var(--tone-info-text)]"
            : "border-[var(--border-subtle)] bg-[rgba(255,255,255,0.03)] text-[var(--text-secondary)]";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-[0.12em] uppercase ${toneClass}`}
    >
      {label}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/*  Tab: Publicacao                                                            */
/* -------------------------------------------------------------------------- */

export function TabPublicacao() {
  const {
    state,
    updateField,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const botId = state.bot.id;
  const hasPendingChanges = Object.values(state.dirty).some(Boolean);

  /* ---------------------------------------------------------------------- */
  /*  Clone                                                                  */
  /* ---------------------------------------------------------------------- */

  async function handleClone() {
    if (!state.cloneDisplayName.trim()) {
      showToast(tl("Nome do clone e obrigatorio."), "warning");
      return;
    }
    const cloneId = state.cloneDisplayName.trim()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9_\s-]/g, "")
      .replace(/[\s-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 80) + `-${Date.now().toString(36)}`;
    await runAction("clone", async () => {
      await requestJson(`/api/control-plane/agents/${botId}/clone`, {
        method: "POST",
        body: JSON.stringify({
          id: cloneId,
          display_name: state.cloneDisplayName.trim(),
        }),
      });
      router.push(`/control-plane/bots/${cloneId}`);
    }, {
      successMessage: tl("Bot clonado com sucesso."),
      errorMessage: tl("Erro ao clonar."),
    });
  }

  /* ---------------------------------------------------------------------- */
  /*  Delete                                                                 */
  /* ---------------------------------------------------------------------- */

  async function handleDelete() {
    setShowDeleteDialog(false);
    await runAction("delete", async () => {
      await requestJson(`/api/control-plane/agents/${botId}`, {
        method: "DELETE",
      });
      router.push("/control-plane");
    }, {
      successMessage: tl("Bot removido."),
      errorMessage: tl("Erro ao remover bot."),
    });
  }

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                 */
  /* ---------------------------------------------------------------------- */

  return (
    <div className="flex flex-col gap-6">
      {/* Change summary */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {tl("Resumo de alteracoes")}
          </h2>
        </div>

        {/* Version info */}
        <div className="flex flex-wrap gap-3">
          <div className="flex flex-col gap-1 border-l border-[var(--border-subtle)] pl-3">
            <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-quaternary)]">
              {tl("Versao publicada")}
            </span>
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {state.bot.applied_version || tl("Nenhuma")}
            </span>
          </div>
          <div className="flex flex-col gap-1 border-l border-[var(--border-subtle)] pl-3">
            <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-quaternary)]">
              {tl("Versao desejada")}
            </span>
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {state.bot.desired_version || tl("Rascunho")}
            </span>
          </div>
          <div className="flex flex-col gap-1 border-l border-[var(--border-subtle)] pl-3">
            <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--text-quaternary)]">
              {tl("Status")}
            </span>
            <PublicationBadge
              label={hasPendingChanges ? tl("Alteracoes pendentes") : tl("Publicado")}
              tone={hasPendingChanges ? "warning" : "success"}
            />
          </div>
        </div>

        {/* Dirty sections list */}
        {hasPendingChanges && (
          <div className="rounded-xl border border-[rgba(255,180,76,0.15)] bg-[rgba(255,180,76,0.03)] px-4 py-3">
            <div className="text-xs font-medium text-[var(--tone-warning-text)] mb-2">
              {tl("Secoes modificadas:")}
            </div>
            <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
              {state.dirty.meta && <li>{"\u2022"} {tl("Identidade e metadados")}</li>}
              {state.dirty.documents && <li>{"\u2022"} {tl("Documentos e instrucoes")}</li>}
              {state.dirty.agentSpec && <li>{"\u2022"} {tl("Especificacao do agente")}</li>}
              {state.dirty.sections && <li>{"\u2022"} {tl("Secoes de configuracao")}</li>}
              {state.dirty.collections && <li>{"\u2022"} {tl("Colecoes de conhecimento")}</li>}
            </ul>
          </div>
        )}
      </section>

      {/* Clone */}
      <section className="border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Clonar agente")}
          icon={Copy}
        >
          <FormInput
            label={tl("Nome do clone")}
            value={state.cloneDisplayName}
            onChange={(e) =>
              updateField("cloneDisplayName", e.target.value)
            }
            placeholder={tl("Copia de...")}
          />
          <div className="flex justify-end">
            <AsyncActionButton
              type="button"
              variant="secondary"
              size="sm"
              disabled={!state.cloneDisplayName.trim()}
              loading={isPending("clone")}
              loadingLabel={tl("Clonando")}
              onClick={handleClone}
            >
              {tl("Clonar agente")}
            </AsyncActionButton>
          </div>
        </PolicyCard>
      </section>

      {/* Danger zone */}
      <section className="border-t border-[var(--border-subtle)] pt-6">
        <div className="flex items-center justify-between">
          <p className="text-xs text-[var(--text-quaternary)]">
            {tl("Remove este agente e todos os dados associados.")}
          </p>
          <button
            type="button"
            onClick={() => setShowDeleteDialog(true)}
            disabled={isPending("delete")}
            className="shrink-0 text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--tone-danger-text)]"
          >
            {isPending("delete") ? tl("Removendo...") : tl("Remover agente")}
          </button>
        </div>
      </section>

      {/* Delete confirmation */}
      <ConfirmationDialog
        open={showDeleteDialog}
        title={tl("Remover agente")}
        message={tl('Tem certeza que deseja remover "{{name}}"? Todas as configuracoes, documentos e versoes serao permanentemente excluidos. Esta acao nao pode ser desfeita.', {
          name: state.displayName || botId,
        })}
        confirmLabel={tl("Remover")}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteDialog(false)}
      />
    </div>
  );
}
