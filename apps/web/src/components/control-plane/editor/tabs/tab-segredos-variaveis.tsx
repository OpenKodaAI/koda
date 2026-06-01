"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { SecretInput } from "@/components/ui/secret-controls";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { CompactGrantToggle } from "@/components/control-plane/shared/compact-grant-toggle";
import { requestJson } from "@/lib/http-client";
import {
  parseResourceAccessPolicy,
  serializeResourceAccessPolicy,
} from "@/lib/policy-serializers";
import { AnimatePresence, motion } from "framer-motion";
import { FADE_TRANSITION } from "@/components/control-plane/shared/motion-constants";
import { cn } from "@/lib/utils";

type SecretSummaryLike = {
  scope: string;
  secret_key: string;
  preview: string;
  grantable_to_agents?: boolean;
  grantable_to_bots?: boolean;
};

function isGrantableSecret(secret: SecretSummaryLike) {
  return (secret.grantable_to_agents ?? secret.grantable_to_bots) !== false;
}

type UnifiedEntry =
  | { kind: "variable"; key: string; value: string }
  | { kind: "secret"; key: string; preview: string };

export function TabSegredosVariaveis() {
  const {
    state,
    systemSettings,
    updateAgentSpecField,
    updateField,
  } = useAgentEditor();
  const { showToast } = useToast();
  const { t } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();

  const [draftKey, setDraftKey] = useState("");
  const [draftValue, setDraftValue] = useState("");
  const [draftIsSecret, setDraftIsSecret] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingKind, setEditingKind] = useState<"variable" | "secret" | null>(null);

  const agentId = state.agent.id;
  const resourcePolicy = useMemo(
    () => parseResourceAccessPolicy(state.resourceAccessPolicyJson),
    [state.resourceAccessPolicyJson],
  );

  const localSecrets = (state.agent.secrets ?? []).filter((item) => {
    const s = String(item.scope || "agent").toLowerCase();
    return s === "agent" || s === "agent";
  });

  const grantableGlobalSecrets = (systemSettings.global_secrets as SecretSummaryLike[]).filter(
    isGrantableSecret,
  );
  const grantedSharedKeys = resourcePolicy.allowed_shared_env_keys;
  const grantedSecretKeys = resourcePolicy.allowed_global_secret_keys;

  const sharedVarOptions = [
    ...systemSettings.shared_variables.map((item) => ({
      value: item.key,
      label: item.key,
      status: t("generated.controlPlane.disponivel_globalmente_da91c50c"),
    })),
    ...grantedSharedKeys
      .filter((key) => !systemSettings.shared_variables.some((item) => item.key === key))
      .map((key) => ({
        value: key,
        label: key,
        status: t("generated.controlPlane.indisponivel_54e299bf"),
      })),
  ];

  const globalSecretOptions = [
    ...grantableGlobalSecrets.map((item) => ({
      value: item.secret_key,
      label: item.secret_key,
      status: t("generated.controlPlane.grantavel_2d9b1b4a"),
    })),
    ...grantedSecretKeys
      .filter((key) => !grantableGlobalSecrets.some((item) => item.secret_key === key))
      .map((key) => {
        const protectedSecret = (systemSettings.global_secrets as SecretSummaryLike[]).find(
          (item) => item.secret_key === key,
        );
        return {
          value: key,
          label: key,
          status:
            protectedSecret && isGrantableSecret(protectedSecret) === false
              ? t("generated.controlPlane.somente_sistema_49d36183")
              : t("generated.controlPlane.indisponivel_54e299bf"),
        };
      }),
  ];

  const localEnvEntries = useMemo(
    () =>
      Object.entries(resourcePolicy.local_env)
        .map(([key, value]) => ({ key, value }))
        .sort((left, right) => left.key.localeCompare(right.key)),
    [resourcePolicy.local_env],
  );

  const unifiedEntries: UnifiedEntry[] = useMemo(() => {
    const items: UnifiedEntry[] = [];
    for (const entry of localEnvEntries) {
      items.push({ kind: "variable", key: entry.key, value: entry.value });
    }
    for (const secret of localSecrets) {
      const secretKey = String(secret.secret_key || "");
      if (secretKey) {
        items.push({ kind: "secret", key: secretKey, preview: String(secret.preview || t("generated.controlPlane.mascarado_18baf8a7")) });
      }
    }
    return items.sort((a, b) => a.key.localeCompare(b.key));
  }, [localEnvEntries, localSecrets, t]);

  function updateResourcePolicy(
    patch: Partial<typeof resourcePolicy>,
  ) {
    updateAgentSpecField(
      "resourceAccessPolicyJson",
      serializeResourceAccessPolicy({ ...resourcePolicy, ...patch }),
    );
  }

  function toggleSelection(items: string[], value: string) {
    return items.includes(value) ? items.filter((item) => item !== value) : [...items, value];
  }

  function handleSharedVarToggle(value: string) {
    updateResourcePolicy({
      allowed_shared_env_keys: toggleSelection(grantedSharedKeys, value),
    });
  }

  function handleGlobalSecretToggle(value: string) {
    updateResourcePolicy({
      allowed_global_secret_keys: toggleSelection(grantedSecretKeys, value),
    });
  }

  function resetEntryForm() {
    setDraftKey("");
    setDraftValue("");
    setDraftIsSecret(false);
    setEditingKey(null);
    setEditingKind(null);
    updateField("secretKey", "");
    updateField("secretValue", "");
  }

  function beginEditVariable(key: string, value: string) {
    setEditingKey(key);
    setEditingKind("variable");
    setDraftKey(key);
    setDraftValue(value);
    setDraftIsSecret(false);
  }

  function beginEditSecret(secretKey: string) {
    setEditingKey(secretKey);
    setEditingKind("secret");
    setDraftKey(secretKey);
    setDraftValue("");
    setDraftIsSecret(true);
    updateField("secretKey", secretKey);
    updateField("secretValue", "");
  }

  function resolveLocalSecretScope(secretKey: string) {
    const matchedSecret = localSecrets.find(
      (secret) => String(secret.secret_key || "").toUpperCase() === secretKey.toUpperCase(),
    );
    return String(matchedSecret?.scope || "agent").toLowerCase() === "agent" ? "agent" : "agent";
  }

  async function handleSaveEntry() {
    const key = draftKey.trim().toUpperCase();
    if (!key) {
      showToast(t("generated.controlPlane.informe_o_nome_da_chave_c14f70d3"), "warning");
      return;
    }

    if (draftIsSecret) {
      const value = draftValue.trim();
      if (!value) {
        showToast(t("generated.controlPlane.informe_o_valor_do_segredo_90374602"), "warning");
        return;
      }
      await runAction("save-secret", async () => {
        const scope = resolveLocalSecretScope(key);
        await requestJson(
          `/api/control-plane/agents/${agentId}/secrets/${encodeURIComponent(key)}?scope=${scope}`,
          {
            method: "PUT",
            body: JSON.stringify({ value }),
          },
        );
        resetEntryForm();
        router.refresh();
      }, {
        successMessage: t("generated.controlPlane.segredo_key_salvo_c55c1208", { key }),
        errorMessage: t("generated.controlPlane.erro_ao_salvar_segredo_5e593bca"),
      });
    } else {
      const value = draftValue.trim();
      if (!value) {
        showToast(t("generated.controlPlane.informe_o_valor_da_variavel_c861c48c"), "warning");
        return;
      }
      const nextLocalEnv = { ...resourcePolicy.local_env };
      if (editingKey && editingKind === "variable" && editingKey !== key) {
        delete nextLocalEnv[editingKey];
      }
      nextLocalEnv[key] = value;
      updateResourcePolicy({ local_env: nextLocalEnv });
      resetEntryForm();
      showToast(t("generated.controlPlane.variavel_key_preparada_no_rascunho_3a26ed53", { key }), "success");
    }
  }

  function handleDeleteVariable(key: string) {
    const next = { ...resourcePolicy.local_env };
    delete next[key];
    updateResourcePolicy({ local_env: next });
    if (editingKey === key) {
      resetEntryForm();
    }
    showToast(t("generated.controlPlane.variavel_key_removida_do_rascunho_60d373cd", { key }), "success");
  }

  async function handleDeleteSecret(key: string) {
    await runAction(`delete-secret:${key}`, async () => {
      const scope = resolveLocalSecretScope(key);
      await requestJson(
        `/api/control-plane/agents/${agentId}/secrets/${encodeURIComponent(key)}?scope=${scope}`,
        { method: "DELETE" },
      );
      if (editingKey === key) {
        resetEntryForm();
      }
      router.refresh();
    }, {
      successMessage: t("generated.controlPlane.segredo_key_removido_88588438", { key }),
      errorMessage: t("generated.controlPlane.erro_ao_remover_segredo_0265953a"),
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={t("generated.controlPlane.escopo_de_acesso_do_agente_3c3b0e67")}
          icon={ShieldCheck}
          dirty={state.dirty.agentSpec}
          variant="flat"
          defaultOpen
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CompactGrantToggle
              title={t("generated.controlPlane.variaveis_compartilhadas_9a4766e6")}
              options={sharedVarOptions}
              selected={grantedSharedKeys}
              onToggle={handleSharedVarToggle}
            />
            <CompactGrantToggle
              title={t("generated.controlPlane.segredos_globais_eda4a8a0")}
              options={globalSecretOptions}
              selected={grantedSecretKeys}
              onToggle={handleGlobalSecretToggle}
            />
          </div>
        </PolicyCard>
      </section>

      <section className="flex flex-col gap-6 border-t border-[color:var(--divider-hair)] pt-6">
        <PolicyCard
          title={t("generated.controlPlane.variaveis_e_segredos_7ebfcfc2")}
          description={t("generated.controlPlane.variaveis_e_credenciais_locais_do_agente_802ae8e1")}
          icon={KeyRound}
          variant="flat"
          defaultOpen
        >
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-[1fr_1fr] gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{t("generated.controlPlane.chave_aa9b585c")}</span>
                <input
                  type="text"
                  className="field-shell font-mono text-[var(--text-primary)]"
                  value={draftKey}
                  onChange={(event) => setDraftKey(event.target.value.toUpperCase())}
                  placeholder="API_KEY"
                  disabled={editingKind === "secret" && Boolean(editingKey)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{t("generated.controlPlane.valor_805659f6")}</span>
                {draftIsSecret ? (
                  <SecretInput
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    placeholder={editingKey ? t("generated.controlPlane.novo_valor_ed960fa6") : t("generated.controlPlane.cole_o_segredo_aqui_7b17e22d")}
                  />
                ) : (
                  <input
                    type="text"
                    className="field-shell text-[var(--text-primary)]"
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    placeholder={t("generated.controlPlane.ex_squad_platform_f98942b9")}
                  />
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setDraftIsSecret((prev) => !prev)}
                disabled={editingKind === "secret"}
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-all",
                  draftIsSecret
                    ? "border-[rgba(255,180,80,0.25)] bg-[rgba(255,180,80,0.08)] text-[rgba(255,200,120,0.9)]"
                    : "border-[var(--border-subtle)] bg-transparent text-[var(--text-tertiary)]",
                  editingKind === "secret" ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-[var(--border-strong)]",
                )}
              >
                <KeyRound size={12} />
                {draftIsSecret ? t("generated.controlPlane.segredo_4e0c54a8") : t("generated.controlPlane.variavel_publica_8a6fb37e")}
              </button>

              <div className="flex items-center gap-2">
                {editingKey && (
                  <button
                    type="button"
                    onClick={resetEntryForm}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)]"
                  >
                    {t("generated.controlPlane.cancelar_091200fb")}
                  </button>
                )}
                <AsyncActionButton
                  type="button"
                  size="sm"
                  loading={draftIsSecret ? isPending("save-secret") : false}
                  loadingLabel={t("generated.controlPlane.salvando_7eeded02")}
                  onClick={handleSaveEntry}
                >
                  {editingKey ? t("generated.controlPlane.salvar_94c457df") : t("generated.controlPlane.adicionar_07558363")}
                </AsyncActionButton>
              </div>
            </div>

            {editingKind === "secret" && editingKey && (
              <p className="text-xs text-[var(--text-quaternary)]">
                {t("generated.controlPlane.substituindo_o_valor_de_0077dbea")}{" "}
                <span className="font-mono text-[var(--text-secondary)]">{editingKey}</span>
                {". "}
                {t("generated.controlPlane.o_valor_atual_continua_mascarado_61b7766e")}
              </p>
            )}
          </div>

          {unifiedEntries.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--text-quaternary)]">
              {t("generated.controlPlane.nenhuma_variavel_ou_segredo_cadastrado_e92517f5")}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <AnimatePresence>
                {unifiedEntries.map((entry) => (
                  <motion.div
                    key={`${entry.kind}:${entry.key}`}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={FADE_TRANSITION}
                  >
                    <div className="flex items-center gap-3 rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3">
                      <div className="flex min-w-0 flex-1 items-center gap-2.5">
                        <span className="font-mono text-sm text-[var(--text-primary)] truncate">{entry.key}</span>
                        <span
                          className={cn(
                            "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
                            entry.kind === "secret"
                              ? "bg-[rgba(255,180,80,0.1)] text-[rgba(255,200,120,0.85)]"
                              : "bg-[rgba(255,255,255,0.05)] text-[var(--text-quaternary)]",
                          )}
                        >
                          {entry.kind === "secret" ? t("generated.controlPlane.secret_21981078") : t("generated.controlPlane.public_388f0dbf")}
                        </span>
                      </div>

                      <span className="hidden font-mono text-xs text-[var(--text-quaternary)] truncate max-w-[200px] md:block">
                        {entry.kind === "secret" ? "••••••••" : entry.value}
                      </span>

                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() =>
                            entry.kind === "variable"
                              ? beginEditVariable(entry.key, entry.value)
                              : beginEditSecret(entry.key)
                          }
                          className="rounded-md p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[rgba(255,255,255,0.06)] hover:text-[var(--text-secondary)]"
                          aria-label={t("generated.controlPlane.editar_28e2e08e")}
                        >
                          <Pencil size={13} />
                        </button>
                        {entry.kind === "variable" ? (
                          <button
                            type="button"
                            onClick={() => handleDeleteVariable(entry.key)}
                            className="rounded-md p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[rgba(255,110,110,0.08)] hover:text-[var(--tone-danger-text)]"
                            aria-label={t("generated.controlPlane.remover_5465770e")}
                          >
                            <Trash2 size={13} />
                          </button>
                        ) : (
                          <AsyncActionButton
                            type="button"
                            variant="danger"
                            size="sm"
                            className="!p-1.5 !rounded-md !border-0 !bg-transparent !shadow-none text-[var(--text-quaternary)] hover:!bg-[rgba(255,110,110,0.08)] hover:!text-[var(--tone-danger-text)]"
                            loading={isPending(`delete-secret:${entry.key}`)}
                            loadingLabel=""
                            onClick={() => handleDeleteSecret(entry.key)}
                            aria-label={t("generated.controlPlane.remover_5465770e")}
                          >
                            <Trash2 size={13} />
                          </AsyncActionButton>
                        )}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </PolicyCard>
      </section>
    </div>
  );
}
