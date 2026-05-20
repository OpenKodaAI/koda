"use client";

import { createPortal } from "react-dom";
import { Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GeneralSystemSettingsVariable } from "@/lib/control-plane";
import { FieldShell } from "./field-shell";
import { SecretInput } from "@/components/ui/secret-controls";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function VariableEditorModal({
  draft,
  onChange,
  onCancel,
  onConfirm,
}: {
  draft: GeneralSystemSettingsVariable;
  onChange: (next: GeneralSystemSettingsVariable) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useAppI18n();
  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        onClick={onCancel}
        aria-hidden="true"
      />
      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel app-modal-anim relative w-full max-w-2xl overflow-hidden border-[var(--border-strong)]"
          onClick={(event) => event.stopPropagation()}
        >
        <button
          type="button"
          onClick={onCancel}
          className="app-surface-close"
          aria-label={t("generated.controlPlane.fechar_modal_1b5b2901")}
        >
          <X className="h-4 w-4" />
        </button>

        <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14 sm:pr-16">
          <div>
            <h3 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {draft.key ? t("generated.controlPlane.editar_variavel_e57d717e") : t("generated.controlPlane.nova_variavel_17e0a7c8")}
            </h3>
            <p className="mt-1 text-sm text-[var(--text-quaternary)]">
              {t("generated.controlPlane.defina_o_tipo_escopo_e_descricao_do_recurso__daf51056")}
            </p>
          </div>
        </div>

        <div className="grid gap-3 px-6 py-5 md:grid-cols-2">
          <FieldShell label={t("generated.controlPlane.nome_fb4c2d32")} description={t("generated.controlPlane.use_um_nome_em_formato_de_variavel_de_ambien_7aba128b")}>
            <input
              className="field-shell text-[var(--text-primary)]"
              value={draft.key}
              onChange={(event) => onChange({ ...draft, key: event.target.value })}
              placeholder="TEAM_NAME"
            />
          </FieldShell>

          <FieldShell label={t("generated.controlPlane.tipo_50772377")} description={t("generated.controlPlane.segredos_ficam_criptografados_e_mascarados_e_cc71b89f")}>
            <Select
              value={draft.type}
              onValueChange={(v) =>
                onChange({ ...draft, type: v === "secret" ? "secret" : "text", clear: false })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="text">{t("generated.controlPlane.texto_f94e22c2")}</SelectItem>
                <SelectItem value="secret">{t("generated.controlPlane.segredo_4e0c54a8")}</SelectItem>
              </SelectContent>
            </Select>
          </FieldShell>

          <FieldShell label={t("generated.controlPlane.escopo_61f1d40b")} description={t("generated.controlPlane.controle_se_o_valor_pode_ser_concedido_expli_0497ea29")}>
            <Select
              value={draft.scope}
              onValueChange={(v) =>
                onChange({ ...draft, scope: v === "agent_grant" ? "agent_grant" : "system_only" })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system_only">{t("generated.controlPlane.somente_sistema_49d36183")}</SelectItem>
                <SelectItem value="agent_grant">{t("generated.controlPlane.disponivel_para_agentes_mediante_grant_43c38b2d")}</SelectItem>
              </SelectContent>
            </Select>
          </FieldShell>

          <FieldShell label={t("generated.controlPlane.descricao_ff40fdea")} description={t("generated.controlPlane.contexto_curto_para_o_operador_lembrar_o_pro_2709d0d5")}>
            <input
              className="field-shell text-[var(--text-primary)]"
              value={draft.description}
              onChange={(event) => onChange({ ...draft, description: event.target.value })}
              placeholder={t("generated.controlPlane.fila_operacional_do_time_1a7f8d7d")}
            />
          </FieldShell>

          <div className="md:col-span-2">
            <FieldShell
              label={draft.type === "secret" ? t("generated.controlPlane.valor_do_segredo_59d42e8d") : t("generated.controlPlane.valor_805659f6")}
              description={
                draft.type === "secret" && draft.value_present
                  ? t(
                      "generated.controlPlane.armazenado_de_forma_criptografada_o_valor_at_a9206a4c",
                    )
                  : t("generated.controlPlane.o_valor_sera_salvo_globalmente_no_control_pl_b83b4c8d")
              }
            >
              <div className="space-y-3">
                {draft.type === "secret" && draft.value_present ? (
                  <span className="inline-flex items-center gap-1 self-start rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                    {t("generated.controlPlane.armazenada_c08c504b")}
                  </span>
                ) : null}
                {draft.type === "secret" ? (
                  <SecretInput
                    value={draft.value}
                    onChange={(event) => onChange({ ...draft, value: event.target.value, clear: false })}
                    placeholder={t("generated.controlPlane.digite_apenas_se_quiser_substituir_486e531c")}
                  />
                ) : (
                  <input
                    className="field-shell text-[var(--text-primary)]"
                    type="text"
                    value={draft.value}
                    onChange={(event) => onChange({ ...draft, value: event.target.value, clear: false })}
                    placeholder={t("generated.controlPlane.valor_f2e480cb")}
                  />
                )}
              </div>
              {draft.type === "secret" && draft.value_present ? (
                <button
                  type="button"
                  onClick={() => onChange({ ...draft, value: "", clear: !draft.clear })}
                  className={cn(
                    "mt-3 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                    draft.clear
                      ? "border-[rgba(255,110,110,0.3)] bg-[rgba(255,110,110,0.12)] text-[var(--tone-danger-text)]"
                      : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                  )}
                >
                  <Trash2 size={14} />
                  {draft.clear ? t("generated.controlPlane.segredo_sera_removido_ao_salvar_38a5d4bc") : t("generated.controlPlane.marcar_para_remover_371dd69b")}
                </button>
              ) : null}
            </FieldShell>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
          >
            {t("generated.controlPlane.cancelar_091200fb")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg bg-[rgba(113,219,190,0.18)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-[rgba(113,219,190,0.24)]"
          >
            {t("generated.controlPlane.aplicar_f2badfb2")}
          </button>
        </div>
      </div>
      </div>
    </>,
    document.body
  );
}
