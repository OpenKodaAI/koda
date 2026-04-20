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
  const { tl } = useAppI18n();
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
      status: tl("Disponivel globalmente"),
    })),
    ...grantedSharedKeys
      .filter((key) => !systemSettings.shared_variables.some((item) => item.key === key))
      .map((key) => ({
        value: key,
        label: key,
        status: tl("Indisponivel"),
      })),
  ];

  const globalSecretOptions = [
    ...grantableGlobalSecrets.map((item) => ({
      value: item.secret_key,
      label: item.secret_key,
      status: tl("Grantavel"),
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
              ? tl("Somente sistema")
              : tl("Indisponivel"),
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
        items.push({ kind: "secret", key: secretKey, preview: String(secret.preview || tl("mascarado")) });
      }
    }
    return items.sort((a, b) => a.key.localeCompare(b.key));
  }, [localEnvEntries, localSecrets, tl]);

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
      showToast(tl("Informe o nome da chave."), "warning");
      return;
    }

    if (draftIsSecret) {
      const value = draftValue.trim();
      if (!value) {
        showToast(tl("Informe o valor do segredo."), "warning");
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
        successMessage: tl('Segredo "{{key}}" salvo.', { key }),
        errorMessage: tl("Erro ao salvar segredo."),
      });
    } else {
      const value = draftValue.trim();
      if (!value) {
        showToast(tl("Informe o valor da variavel."), "warning");
        return;
      }
      const nextLocalEnv = { ...resourcePolicy.local_env };
      if (editingKey && editingKind === "variable" && editingKey !== key) {
        delete nextLocalEnv[editingKey];
      }
      nextLocalEnv[key] = value;
      updateResourcePolicy({ local_env: nextLocalEnv });
      resetEntryForm();
      showToast(tl('Variavel "{{key}}" preparada no rascunho.', { key }), "success");
    }
  }

  function handleDeleteVariable(key: string) {
    const next = { ...resourcePolicy.local_env };
    delete next[key];
    updateResourcePolicy({ local_env: next });
    if (editingKey === key) {
      resetEntryForm();
    }
    showToast(tl('Variavel "{{key}}" removida do rascunho.', { key }), "success");
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
      successMessage: tl('Segredo "{{key}}" removido.', { key }),
      errorMessage: tl("Erro ao remover segredo."),
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={tl("Escopo de acesso do agente")}
          icon={ShieldCheck}
          dirty={state.dirty.agentSpec}
          variant="flat"
          defaultOpen
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CompactGrantToggle
              title={tl("Variaveis compartilhadas")}
              options={sharedVarOptions}
              selected={grantedSharedKeys}
              onToggle={handleSharedVarToggle}
            />
            <CompactGrantToggle
              title={tl("Segredos globais")}
              options={globalSecretOptions}
              selected={grantedSecretKeys}
              onToggle={handleGlobalSecretToggle}
            />
          </div>
        </PolicyCard>
      </section>

      <section className="flex flex-col gap-6 border-t border-[color:var(--divider-hair)] pt-6">
        <PolicyCard
          title={tl("Variaveis e segredos")}
          description={tl("Variaveis e credenciais locais do agente.")}
          icon={KeyRound}
          variant="flat"
          defaultOpen
        >
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-[1fr_1fr] gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{tl("Chave")}</span>
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
                <span className="eyebrow">{tl("Valor")}</span>
                {draftIsSecret ? (
                  <SecretInput
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    placeholder={editingKey ? tl("Novo valor") : tl("Cole o segredo aqui")}
                  />
                ) : (
                  <input
                    type="text"
                    className="field-shell text-[var(--text-primary)]"
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    placeholder={tl("Ex.: squad-platform")}
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
                {draftIsSecret ? tl("Segredo") : tl("Variavel publica")}
              </button>

              <div className="flex items-center gap-2">
                {editingKey && (
                  <button
                    type="button"
                    onClick={resetEntryForm}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)]"
                  >
                    {tl("Cancelar")}
                  </button>
                )}
                <AsyncActionButton
                  type="button"
                  size="sm"
                  loading={draftIsSecret ? isPending("save-secret") : false}
                  loadingLabel={tl("Salvando")}
                  onClick={handleSaveEntry}
                >
                  {editingKey ? tl("Salvar") : tl("Adicionar")}
                </AsyncActionButton>
              </div>
            </div>

            {editingKind === "secret" && editingKey && (
              <p className="text-xs text-[var(--text-quaternary)]">
                {tl("Substituindo o valor de")}{" "}
                <span className="font-mono text-[var(--text-secondary)]">{editingKey}</span>
                {". "}
                {tl("O valor atual continua mascarado.")}
              </p>
            )}
          </div>

          {unifiedEntries.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--text-quaternary)]">
              {tl("Nenhuma variavel ou segredo cadastrado.")}
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
                          {entry.kind === "secret" ? tl("secret") : tl("public")}
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
                          aria-label={tl("Editar")}
                        >
                          <Pencil size={13} />
                        </button>
                        {entry.kind === "variable" ? (
                          <button
                            type="button"
                            onClick={() => handleDeleteVariable(entry.key)}
                            className="rounded-md p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[rgba(255,110,110,0.08)] hover:text-[var(--tone-danger-text)]"
                            aria-label={tl("Remover")}
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
                            aria-label={tl("Remover")}
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
