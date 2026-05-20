"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { KeyRound, Pencil, Trash2, Users, Lock } from "lucide-react";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { FADE_TRANSITION } from "@/components/control-plane/shared/motion-constants";
import { Button } from "@/components/ui/button";
import { SecretInput } from "@/components/ui/secret-controls";
import { translate } from "@/lib/i18n";
import {
  removeVariable,
  sanitizeVariableDraft,
  upsertVariable,
} from "@/lib/system-settings-model";
import { findFieldError } from "@/lib/system-settings-schema";
import type { GeneralSystemSettingsVariable } from "@/lib/control-plane";
import { cn } from "@/lib/utils";

type DraftState = {
  key: string;
  value: string;
  description: string;
  type: "text" | "secret";
  scope: "system_only" | "agent_grant";
  clear: boolean;
  valuePresent: boolean;
  preview: string;
};

const INITIAL_DRAFT: DraftState = {
  key: "",
  value: "",
  description: "",
  type: "text",
  scope: "system_only",
  clear: false,
  valuePresent: false,
  preview: "",
};

export function SectionVariables() {
  const { draft, setField, sectionErrors } = useSystemSettings();
  const { t, tl } = useAppI18n();
  const { showToast } = useToast();
  const variables = draft.values.variables;
  const variableErrors = sectionErrors.variables;

  const [entryDraft, setEntryDraft] = useState<DraftState>(INITIAL_DRAFT);
  const [editingKey, setEditingKey] = useState<string | null>(null);

  const sortedVariables = useMemo(
    () => [...variables].sort((a, b) => a.key.localeCompare(b.key)),
    [variables],
  );

  // Map error field path "variables.{index}.x" back to the key, so we can flag
  // the offending row in the list even though save ordered them alphabetically.
  const errorKeysByIndex = useMemo(() => {
    const keys = new Set<string>();
    for (const err of variableErrors) {
      const match = /^variables\.(\d+)(?:\.|$)/.exec(err.field);
      if (!match) continue;
      const idx = Number(match[1]);
      if (Number.isInteger(idx) && idx >= 0 && idx < variables.length) {
        keys.add(variables[idx]!.key);
      }
    }
    return keys;
  }, [variableErrors, variables]);

  const draftKeyError = useMemo(() => {
    if (!editingKey) return undefined;
    const idx = variables.findIndex((variable) => variable.key === editingKey);
    if (idx < 0) return undefined;
    return (
      findFieldError(variableErrors, `variables.${idx}.key`)?.message ??
      findFieldError(variableErrors, `variables.${idx}.type`)?.message ??
      findFieldError(variableErrors, `variables.${idx}.scope`)?.message
    );
  }, [editingKey, variables, variableErrors]);

  const isEditing = editingKey !== null;

  function resetDraft() {
    setEntryDraft(INITIAL_DRAFT);
    setEditingKey(null);
  }

  function beginEdit(variable: GeneralSystemSettingsVariable) {
    setEditingKey(variable.key);
    setEntryDraft({
      key: variable.key,
      value: "",
      description: variable.description,
      type: variable.type,
      scope: variable.scope,
      clear: false,
      valuePresent: variable.value_present,
      preview: variable.preview,
    });
  }

  function handleSave() {
    const key = entryDraft.key.trim().toUpperCase();
    if (!key) {
      showToast(t("generated.controlPlane.informe_o_nome_da_variavel_b665fcbe"), "warning");
      return;
    }

    const trimmedValue = entryDraft.value.trim();

    if (entryDraft.type === "text" && !trimmedValue) {
      showToast(t("generated.controlPlane.informe_um_valor_para_a_variavel_2d9c881a"), "warning");
      return;
    }

    if (entryDraft.type === "secret" && !trimmedValue && !entryDraft.valuePresent && !entryDraft.clear) {
      showToast(t("generated.controlPlane.informe_um_valor_inicial_para_o_segredo_a537a83e"), "warning");
      return;
    }

    const sanitized = sanitizeVariableDraft({
      key,
      type: entryDraft.type,
      scope: entryDraft.scope,
      description: entryDraft.description,
      value: entryDraft.value,
      preview: entryDraft.preview,
      value_present: entryDraft.valuePresent,
      clear: entryDraft.clear,
    });

    const baseVariables =
      editingKey && editingKey !== sanitized.key
        ? removeVariable(variables, editingKey)
        : variables;

    setField("variables", upsertVariable(baseVariables, sanitized));
    showToast(t("generated.controlPlane.variavel_key_preparada_no_rascunho_0413664f", { key: sanitized.key }), "success");
    resetDraft();
  }

  function handleDelete(variableKey: string) {
    setField("variables", removeVariable(variables, variableKey));
    if (editingKey === variableKey) {
      resetDraft();
    }
    showToast(t("generated.controlPlane.variavel_key_removida_do_rascunho_808b7ee2", { key: variableKey }), "success");
  }

  return (
    <SettingsSectionShell
      sectionId="variables"
      title={translate("generated.controlPlane.settings_sections_variables_label_3aca0db4")}
      description={translate("generated.controlPlane.settings_sections_variables_description_850103a5")}
    >
      <SettingsFieldGroup title={t("generated.controlPlane.variaveis_e_segredos_7c5649cf")}>
        <PolicyCard
          title={t("generated.controlPlane.variaveis_e_segredos_do_sistema_94c2c439")}
          description={t("generated.controlPlane.recursos_globais_disponiveis_para_agentes_me_2102fe19")}
          icon={KeyRound}
          variant="flat"
          defaultOpen
        >
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{t("generated.controlPlane.chave_aa9b585c")}</span>
                <input
                  type="text"
                  className={cn(
                    "field-shell font-mono text-[var(--text-primary)]",
                    draftKeyError
                      ? "border-[var(--tone-danger-border)] focus:border-[var(--tone-danger-border)]"
                      : "",
                  )}
                  value={entryDraft.key}
                  onChange={(event) =>
                    setEntryDraft((prev) => ({
                      ...prev,
                      key: event.target.value.toUpperCase(),
                    }))
                  }
                  placeholder="TEAM_NAME"
                  disabled={isEditing && entryDraft.type === "secret"}
                  aria-invalid={draftKeyError ? true : undefined}
                />
                {draftKeyError ? (
                  <span role="alert" className="text-xs text-[var(--tone-danger-text)]">
                    {tl(draftKeyError)}
                  </span>
                ) : null}
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">
                  {entryDraft.type === "secret" ? t("generated.controlPlane.valor_do_segredo_59d42e8d") : t("generated.controlPlane.valor_805659f6")}
                </span>
                {entryDraft.type === "secret" ? (
                  <SecretInput
                    value={entryDraft.value}
                    onChange={(event) =>
                      setEntryDraft((prev) => ({
                        ...prev,
                        value: event.target.value,
                        clear: false,
                      }))
                    }
                    placeholder={
                      entryDraft.valuePresent
                        ? t("generated.controlPlane.digite_apenas_se_quiser_substituir_486e531c")
                        : t("generated.controlPlane.cole_o_segredo_aqui_7b17e22d")
                    }
                  />
                ) : (
                  <input
                    type="text"
                    className="field-shell text-[var(--text-primary)]"
                    value={entryDraft.value}
                    onChange={(event) =>
                      setEntryDraft((prev) => ({ ...prev, value: event.target.value }))
                    }
                    placeholder={t("generated.controlPlane.ex_squad_platform_f98942b9")}
                  />
                )}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="eyebrow">{t("generated.controlPlane.descricao_ff40fdea")}</span>
              <input
                type="text"
                className="field-shell text-[var(--text-primary)]"
                value={entryDraft.description}
                onChange={(event) =>
                  setEntryDraft((prev) => ({ ...prev, description: event.target.value }))
                }
                placeholder={t("generated.controlPlane.contexto_curto_para_o_operador_lembrar_o_pro_2709d0d5")}
              />
            </div>

            {entryDraft.type === "secret" && entryDraft.valuePresent ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
                    {t("generated.controlPlane.armazenada_c08c504b")}
                  </span>
                  <span className="text-xs text-[var(--text-tertiary)]">
                    {t(
                      "generated.controlPlane.o_valor_atual_nunca_e_exibido_digite_uma_nov_df7194d3",
                    )}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setEntryDraft((prev) => ({ ...prev, clear: !prev.clear, value: "" }))
                  }
                  className={cn(
                    "inline-flex items-center gap-2 self-start rounded-[var(--radius-panel-sm)] border px-3 py-1.5 text-xs transition-colors",
                    entryDraft.clear
                      ? "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]"
                      : "border-[var(--border-subtle)] bg-transparent text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)]",
                  )}
                >
                  <Trash2 size={13} strokeWidth={1.75} />
                  {entryDraft.clear
                    ? t("generated.controlPlane.segredo_sera_removido_ao_salvar_38a5d4bc")
                    : t("generated.controlPlane.marcar_para_remover_371dd69b")}
                </button>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() =>
                    setEntryDraft((prev) => ({
                      ...prev,
                      type: prev.type === "secret" ? "text" : "secret",
                      value: "",
                      clear: false,
                    }))
                  }
                  disabled={isEditing}
                  aria-pressed={entryDraft.type === "secret"}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-[var(--radius-panel-sm)] border px-2.5 py-1.5 text-xs font-medium transition-colors",
                    entryDraft.type === "secret"
                      ? "border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]"
                      : "border-[var(--border-subtle)] bg-transparent text-[var(--text-tertiary)]",
                    isEditing
                      ? "cursor-not-allowed opacity-50"
                      : "cursor-pointer hover:border-[var(--border-strong)]",
                  )}
                >
                  <KeyRound size={12} strokeWidth={1.75} />
                  {entryDraft.type === "secret" ? t("generated.controlPlane.segredo_4e0c54a8") : t("generated.controlPlane.texto_publico_e7ca87e6")}
                </button>

                <button
                  type="button"
                  onClick={() =>
                    setEntryDraft((prev) => ({
                      ...prev,
                      scope: prev.scope === "agent_grant" ? "system_only" : "agent_grant",
                    }))
                  }
                  aria-pressed={entryDraft.scope === "agent_grant"}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-[var(--radius-panel-sm)] border px-2.5 py-1.5 text-xs font-medium transition-colors cursor-pointer",
                    entryDraft.scope === "agent_grant"
                      ? "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]"
                      : "border-[var(--border-subtle)] bg-transparent text-[var(--text-tertiary)] hover:border-[var(--border-strong)]",
                  )}
                >
                  {entryDraft.scope === "agent_grant" ? (
                    <Users size={12} strokeWidth={1.75} />
                  ) : (
                    <Lock size={12} strokeWidth={1.75} />
                  )}
                  {entryDraft.scope === "agent_grant"
                    ? t("generated.controlPlane.disponivel_por_grant_2133c406")
                    : t("generated.controlPlane.somente_sistema_49d36183")}
                </button>
              </div>

              <div className="flex items-center gap-2">
                {isEditing ? (
                  <Button type="button" variant="ghost" size="sm" onClick={resetDraft}>
                    {t("generated.controlPlane.cancelar_091200fb")}
                  </Button>
                ) : null}
                <Button type="button" variant="accent" size="sm" onClick={handleSave}>
                  {isEditing ? t("generated.controlPlane.salvar_94c457df") : t("generated.controlPlane.adicionar_07558363")}
                </Button>
              </div>
            </div>
          </div>

          {sortedVariables.length === 0 ? (
            <div className="rounded-[var(--radius-panel-sm)] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--text-quaternary)]">
              {t("generated.controlPlane.nenhuma_variavel_global_customizada_foi_adic_71e7f5d7")}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <AnimatePresence initial={false}>
                {sortedVariables.map((variable) => {
                  const isRowEditing = editingKey === variable.key;
                  const rowHasError = errorKeysByIndex.has(variable.key);
                  return (
                    <motion.div
                      key={variable.key}
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={FADE_TRANSITION}
                    >
                      <div
                        className={cn(
                          "flex flex-col gap-1 rounded-[var(--radius-panel-sm)] border px-3.5 py-2.5 transition-colors",
                          rowHasError
                            ? "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)]"
                            : isRowEditing
                              ? "border-[var(--border-strong)] bg-[var(--hover-tint)]"
                              : "border-[var(--border-subtle)] bg-[var(--panel-soft)]",
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex min-w-0 flex-1 items-center gap-2">
                            <span className="truncate font-mono text-sm text-[var(--text-primary)]">
                              {variable.key}
                            </span>
                            <span
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
                                variable.type === "secret"
                                  ? "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]"
                                  : "bg-[var(--hover-tint)] text-[var(--text-quaternary)]",
                              )}
                            >
                              {variable.type === "secret" ? t("generated.controlPlane.secret_21981078") : t("generated.controlPlane.public_388f0dbf")}
                            </span>
                            <span
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
                                variable.scope === "agent_grant"
                                  ? "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]"
                                  : "bg-[var(--hover-tint)] text-[var(--text-quaternary)]",
                              )}
                            >
                              {variable.scope === "agent_grant" ? t("generated.controlPlane.grant_359fdf66") : t("generated.controlPlane.system_c5d2946b")}
                            </span>
                          </div>

                          <span className="hidden max-w-[220px] truncate font-mono text-xs text-[var(--text-quaternary)] md:inline">
                            {variable.type === "secret"
                              ? t("generated.controlPlane.segredo_armazenado_bb36dd53")
                              : variable.value}
                          </span>

                          <div className="flex shrink-0 items-center gap-0.5">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => beginEdit(variable)}
                              aria-label={t("generated.controlPlane.editar_28e2e08e")}
                              className="px-2"
                            >
                              <Pencil size={13} strokeWidth={1.75} />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(variable.key)}
                              aria-label={t("generated.controlPlane.remover_5465770e")}
                              className="px-2 text-[var(--text-quaternary)] hover:text-[var(--tone-danger-text)]"
                            >
                              <Trash2 size={13} strokeWidth={1.75} />
                            </Button>
                          </div>
                        </div>
                        {variable.description ? (
                          <p className="text-xs text-[var(--text-quaternary)]">
                            {variable.description}
                          </p>
                        ) : null}
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          )}
        </PolicyCard>
      </SettingsFieldGroup>
    </SettingsSectionShell>
  );
}
