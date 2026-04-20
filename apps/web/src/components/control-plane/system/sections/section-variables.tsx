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
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";
import {
  removeVariable,
  sanitizeVariableDraft,
  upsertVariable,
} from "@/lib/system-settings-model";
import type { GeneralSystemSettingsVariable } from "@/lib/control-plane";
import { cn } from "@/lib/utils";

type DraftState = {
  key: string;
  value: string;
  description: string;
  type: "text" | "secret";
  scope: "system_only" | "bot_grant";
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
  const { draft, setField } = useSystemSettings();
  const { tl } = useAppI18n();
  const { showToast } = useToast();
  const variables = draft.values.variables;

  const [entryDraft, setEntryDraft] = useState<DraftState>(INITIAL_DRAFT);
  const [editingKey, setEditingKey] = useState<string | null>(null);

  const sortedVariables = useMemo(
    () => [...variables].sort((a, b) => a.key.localeCompare(b.key)),
    [variables],
  );

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
      showToast(tl("Informe o nome da variável."), "warning");
      return;
    }

    const trimmedValue = entryDraft.value.trim();

    if (entryDraft.type === "text" && !trimmedValue) {
      showToast(tl("Informe um valor para a variável."), "warning");
      return;
    }

    if (entryDraft.type === "secret" && !trimmedValue && !entryDraft.valuePresent && !entryDraft.clear) {
      showToast(tl("Informe um valor inicial para o segredo."), "warning");
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
    showToast(tl('Variável "{{key}}" preparada no rascunho.', { key: sanitized.key }), "success");
    resetDraft();
  }

  function handleDelete(variableKey: string) {
    setField("variables", removeVariable(variables, variableKey));
    if (editingKey === variableKey) {
      resetDraft();
    }
    showToast(tl('Variável "{{key}}" removida do rascunho.', { key: variableKey }), "success");
  }

  return (
    <SettingsSectionShell
      sectionId="variables"
      title="settings.sections.variables.label"
      description="settings.sections.variables.description"
    >
      <SettingsFieldGroup title={tl("Variáveis e segredos")}>
        <PolicyCard
          title={tl("Variáveis e segredos do sistema")}
          description={tl("Recursos globais disponíveis para agentes mediante grant explícito.")}
          icon={KeyRound}
          variant="flat"
          defaultOpen
        >
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{tl("Chave")}</span>
                <input
                  type="text"
                  className="field-shell font-mono text-[var(--text-primary)]"
                  value={entryDraft.key}
                  onChange={(event) =>
                    setEntryDraft((prev) => ({
                      ...prev,
                      key: event.target.value.toUpperCase(),
                    }))
                  }
                  placeholder="TEAM_NAME"
                  disabled={isEditing && entryDraft.type === "secret"}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">
                  {entryDraft.type === "secret" ? tl("Valor do segredo") : tl("Valor")}
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
                        ? tl("Digite apenas se quiser substituir")
                        : tl("Cole o segredo aqui")
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
                    placeholder={tl("Ex.: squad-platform")}
                  />
                )}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="eyebrow">{tl("Descrição")}</span>
              <input
                type="text"
                className="field-shell text-[var(--text-primary)]"
                value={entryDraft.description}
                onChange={(event) =>
                  setEntryDraft((prev) => ({ ...prev, description: event.target.value }))
                }
                placeholder={tl("Contexto curto para o operador lembrar o propósito.")}
              />
            </div>

            {entryDraft.type === "secret" && entryDraft.valuePresent ? (
              <div className="flex flex-col gap-2">
                <MaskedSecretPreview preview={entryDraft.preview} />
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
                    ? tl("Segredo será removido ao salvar")
                    : tl("Marcar para remover")}
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
                  {entryDraft.type === "secret" ? tl("Segredo") : tl("Texto público")}
                </button>

                <button
                  type="button"
                  onClick={() =>
                    setEntryDraft((prev) => ({
                      ...prev,
                      scope: prev.scope === "bot_grant" ? "system_only" : "bot_grant",
                    }))
                  }
                  aria-pressed={entryDraft.scope === "bot_grant"}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-[var(--radius-panel-sm)] border px-2.5 py-1.5 text-xs font-medium transition-colors cursor-pointer",
                    entryDraft.scope === "bot_grant"
                      ? "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]"
                      : "border-[var(--border-subtle)] bg-transparent text-[var(--text-tertiary)] hover:border-[var(--border-strong)]",
                  )}
                >
                  {entryDraft.scope === "bot_grant" ? (
                    <Users size={12} strokeWidth={1.75} />
                  ) : (
                    <Lock size={12} strokeWidth={1.75} />
                  )}
                  {entryDraft.scope === "bot_grant"
                    ? tl("Disponível por grant")
                    : tl("Somente sistema")}
                </button>
              </div>

              <div className="flex items-center gap-2">
                {isEditing ? (
                  <Button type="button" variant="ghost" size="sm" onClick={resetDraft}>
                    {tl("Cancelar")}
                  </Button>
                ) : null}
                <Button type="button" variant="accent" size="sm" onClick={handleSave}>
                  {isEditing ? tl("Salvar") : tl("Adicionar")}
                </Button>
              </div>
            </div>
          </div>

          {sortedVariables.length === 0 ? (
            <div className="rounded-[var(--radius-panel-sm)] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--text-quaternary)]">
              {tl("Nenhuma variável global customizada foi adicionada ainda.")}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <AnimatePresence initial={false}>
                {sortedVariables.map((variable) => {
                  const isRowEditing = editingKey === variable.key;
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
                          isRowEditing
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
                              {variable.type === "secret" ? tl("secret") : tl("public")}
                            </span>
                            <span
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
                                variable.scope === "bot_grant"
                                  ? "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]"
                                  : "bg-[var(--hover-tint)] text-[var(--text-quaternary)]",
                              )}
                            >
                              {variable.scope === "bot_grant" ? tl("grant") : tl("system")}
                            </span>
                          </div>

                          <span className="hidden max-w-[220px] truncate font-mono text-xs text-[var(--text-quaternary)] md:inline">
                            {variable.type === "secret"
                              ? variable.preview || "••••••••"
                              : variable.value}
                          </span>

                          <div className="flex shrink-0 items-center gap-0.5">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => beginEdit(variable)}
                              aria-label={tl("Editar")}
                              className="px-2"
                            >
                              <Pencil size={13} strokeWidth={1.75} />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(variable.key)}
                              aria-label={tl("Remover")}
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
