"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, KeyRound, Pencil, ShieldCheck, Trash2, X } from "lucide-react";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { MaskedSecretPreview, SecretInput } from "@/components/ui/secret-controls";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { FormInput } from "@/components/control-plane/shared/form-field";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { requestJson } from "@/lib/http-client";
import {
  parseResourceAccessPolicy,
  serializeResourceAccessPolicy,
} from "@/lib/policy-serializers";
import { cn } from "@/lib/utils";

function ScopePill({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "accent";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium",
        tone === "accent"
          ? "bg-[rgba(113,219,190,0.12)] text-[var(--text-primary)]"
          : "bg-[rgba(255,255,255,0.04)] text-[var(--text-secondary)]",
      )}
    >
      {label}
    </span>
  );
}

type AccessOption = {
  value: string;
  title: string;
  description: string;
  status: string;
};

function ResourceListCard({
  title,
  description,
  children,
  countLabel,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  countLabel?: string;
}) {
  return (
    <section className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-quaternary)]">{description}</p>
        </div>
        {countLabel ? <ScopePill label={countLabel} /> : null}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function AccessGrantList({
  title,
  description,
  options,
  selected,
  emptyMessage,
  onToggle,
}: {
  title: string;
  description: string;
  options: AccessOption[];
  selected: string[];
  emptyMessage: string;
  onToggle: (value: string) => void;
}) {
  const { tl } = useAppI18n();

  return (
    <ResourceListCard
      title={title}
      description={description}
      countLabel={tl("{{selected}}/{{total}} concedido(s)", {
        selected: selected.length,
        total: options.length || 0,
      })}
    >
      {options.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
          {emptyMessage}
        </div>
      ) : (
        <div className="space-y-2.5">
          {options.map((option) => {
            const selectedNow = selected.includes(option.value);
            const blockedStatus =
              option.status === tl("Somente sistema") || option.status === tl("Indisponível");
            const disabled = !selectedNow && blockedStatus;

            return (
              <div
                key={option.value}
                className="rounded-xl border border-[rgba(255,255,255,0.05)] bg-[rgba(255,255,255,0.018)] px-4 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="min-w-0 break-all font-mono text-sm text-[var(--text-primary)]">
                        {option.title}
                      </span>
                      <ScopePill
                        label={option.status}
                        tone={
                          option.status === tl("Grantável") ||
                          option.status === tl("Disponível globalmente")
                            ? "accent"
                            : "neutral"
                        }
                      />
                      {selectedNow ? <ScopePill label={tl("Concedido")} tone="accent" /> : null}
                    </div>
                    <p className="mt-1.5 break-words text-xs leading-relaxed text-[var(--text-quaternary)]">
                      {option.description}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => onToggle(option.value)}
                    disabled={disabled}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      selectedNow
                        ? "border border-[rgba(255,110,110,0.18)] text-[var(--tone-danger-text)] hover:bg-[rgba(255,110,110,0.08)]"
                        : "bg-[rgba(113,219,190,0.16)] text-[var(--text-primary)] hover:bg-[rgba(113,219,190,0.24)]",
                      disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
                    )}
                  >
                    {selectedNow ? <X size={14} /> : <Check size={14} />}
                    {selectedNow ? tl("Remover acesso") : tl("Conceder acesso")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </ResourceListCard>
  );
}

export function TabEscopo() {
  const {
    state,
    systemSettings,
    updateAgentSpecField,
    updateField,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();
  const [localEnvDraft, setLocalEnvDraft] = useState({ key: "", value: "" });
  const [editingEnvKey, setEditingEnvKey] = useState<string | null>(null);
  const [editingLocalSecretKey, setEditingLocalSecretKey] = useState<string | null>(null);

  const botId = state.bot.id;
  const resourcePolicy = useMemo(
    () => parseResourceAccessPolicy(state.resourceAccessPolicyJson),
    [state.resourceAccessPolicyJson],
  );
  const localSecrets = (state.bot.secrets ?? []).filter((item) => String(item.scope || "bot") === "bot");
  const sharedVariableOptions = systemSettings.shared_variables.map((item) => ({
    value: item.key,
    title: item.key,
    description: item.value || tl("Sem valor configurado"),
    status: tl("Disponível globalmente"),
  }));
  const grantableGlobalSecrets = systemSettings.global_secrets.filter(
    (item) => item.grantable_to_bots !== false,
  );
  const grantedSharedKeys = resourcePolicy.allowed_shared_env_keys;
  const grantedSecretKeys = resourcePolicy.allowed_global_secret_keys;
  const secretOptions = [
    ...grantableGlobalSecrets.map((item) => ({
      value: item.secret_key,
      title: item.secret_key,
      description: item.preview || tl("Mascarado"),
      status: tl("Grantável"),
    })),
    ...grantedSecretKeys
      .filter((key) => !grantableGlobalSecrets.some((item) => item.secret_key === key))
      .map((key) => {
        const protectedSecret = systemSettings.global_secrets.find((item) => item.secret_key === key);
        return {
          value: key,
          title: key,
          description:
            protectedSecret?.preview ||
            (protectedSecret && protectedSecret.grantable_to_bots === false
              ? tl("Protegido no sistema")
              : tl("Não encontrado no vault atual")),
          status:
            protectedSecret && protectedSecret.grantable_to_bots === false
              ? tl("Somente sistema")
              : tl("Indisponível"),
        };
      }),
  ];
  const sharedOptions = [
    ...sharedVariableOptions,
    ...grantedSharedKeys
      .filter((key) => !systemSettings.shared_variables.some((item) => item.key === key))
      .map((key) => ({
        value: key,
        title: key,
        description: tl("Não encontrado nas variáveis globais atuais"),
        status: tl("Indisponível"),
      })),
  ];
  const localEnvEntries = useMemo(
    () =>
      Object.entries(resourcePolicy.local_env)
        .map(([key, value]) => ({ key, value }))
        .sort((left, right) => left.key.localeCompare(right.key)),
    [resourcePolicy.local_env],
  );

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

  function resetLocalSecretEditor() {
    setEditingLocalSecretKey(null);
    updateField("secretKey", "");
    updateField("secretValue", "");
  }

  function beginEditLocalSecret(secretKey: string) {
    setEditingLocalSecretKey(secretKey);
    updateField("secretKey", secretKey);
    updateField("secretValue", "");
  }

  function handleEditLocalEnv(key: string, value: string) {
    setEditingEnvKey(key);
    setLocalEnvDraft({ key, value });
  }

  function handleCancelLocalEnv() {
    setEditingEnvKey(null);
    setLocalEnvDraft({ key: "", value: "" });
  }

  function handleSaveLocalEnv() {
    const key = localEnvDraft.key.trim().toUpperCase();
    const value = localEnvDraft.value.trim();
    if (!key) {
      showToast(tl("Informe o nome da variável local."), "warning");
      return;
    }
    if (!value) {
      showToast(tl("Informe o valor da variável local."), "warning");
      return;
    }
    const nextLocalEnv = { ...resourcePolicy.local_env };
    if (editingEnvKey && editingEnvKey !== key) {
      delete nextLocalEnv[editingEnvKey];
    }
    nextLocalEnv[key] = value;
    updateResourcePolicy({
      local_env: nextLocalEnv,
    });
    handleCancelLocalEnv();
    showToast(tl('Variável local "{{key}}" preparada no rascunho.', { key }), "success");
  }

  function handleDeleteLocalEnv(key: string) {
    const next = { ...resourcePolicy.local_env };
    delete next[key];
    updateResourcePolicy({ local_env: next });
    if (editingEnvKey === key) {
      handleCancelLocalEnv();
    }
    showToast(tl('Variável local "{{key}}" removida do rascunho.', { key }), "success");
  }

  async function handleSaveLocalSecret() {
    const key = state.secretKey.trim().toUpperCase();
    const value = state.secretValue.trim();
    if (!key) {
      showToast(tl("Informe o nome do segredo local."), "warning");
      return;
    }
    if (!value) {
      showToast(tl("Informe o valor do segredo local."), "warning");
      return;
    }

    await runAction("save-secret", async () => {
      await requestJson(`/api/control-plane/agents/${botId}/secrets/${encodeURIComponent(key)}?scope=bot`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      });
      resetLocalSecretEditor();
      router.refresh();
    }, {
      successMessage: tl('Segredo local "{{key}}" salvo.', { key }),
      errorMessage: tl("Erro ao salvar segredo local."),
    });
  }

  async function handleDeleteLocalSecret(key: string) {
    await runAction(`delete-secret:${key}`, async () => {
      await requestJson(`/api/control-plane/agents/${botId}/secrets/${encodeURIComponent(key)}?scope=bot`, {
        method: "DELETE",
      });
      if (editingLocalSecretKey === key) {
        resetLocalSecretEditor();
      }
      router.refresh();
    }, {
      successMessage: tl('Segredo local "{{key}}" removido.', { key }),
      errorMessage: tl("Erro ao remover segredo local."),
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <PolicyCard
          title={tl("Escopo de acesso do agente")}
          description={tl("Defina exatamente quais recursos globais este agente pode receber do sistema.")}
          icon={ShieldCheck}
          dirty={state.dirty.agentSpec}
        >
          <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3 text-sm leading-relaxed text-[var(--text-quaternary)]">
            {tl("As configurações globais valem para toda a conta, mas este agente só recebe variáveis e segredos quando o grant estiver marcado abaixo. Tools, providers e demais capacidades continuam governados na aba Recursos.")}
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <AccessGrantList
              title={tl("Variáveis compartilhadas")}
              description={tl("Valores globais não sensíveis que este agente pode receber do sistema.")}
              options={sharedOptions}
              selected={grantedSharedKeys}
              emptyMessage={tl("Nenhuma variável global disponível ainda. Crie-as primeiro em Configurações gerais.")}
              onToggle={(value) =>
                updateResourcePolicy({
                  allowed_shared_env_keys: toggleSelection(grantedSharedKeys, value),
                })
              }
            />

            <AccessGrantList
              title={tl("Segredos globais")}
              description={tl("Segredos criptografados do vault global. O bot só recebe o que for explicitamente concedido.")}
              options={secretOptions}
              selected={grantedSecretKeys}
              emptyMessage={tl("Nenhum segredo global disponível ainda. Cadastre-os primeiro em Configurações gerais.")}
              onToggle={(value) =>
                updateResourcePolicy({
                  allowed_global_secret_keys: toggleSelection(grantedSecretKeys, value),
                })
              }
            />
          </div>
        </PolicyCard>
      </section>

      <section className="flex flex-col gap-6 border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Variáveis locais do agente")}
          description={tl("Valores não sensíveis usados somente por este agente. Segredos devem ficar no vault local abaixo.")}
          icon={ShieldCheck}
        >
          <ResourceListCard
            title={editingEnvKey ? tl("Editar variável local") : tl("Nova variável local")}
            description={tl("Use esta área para dados exclusivos do agente que não sejam sensíveis.")}
            countLabel={tl("{{count}} item(ns)", { count: localEnvEntries.length })}
          >
            <div className="grid gap-3 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_auto]">
              <FormInput
                label={tl("Nome")}
                value={localEnvDraft.key}
                onChange={(event) =>
                  setLocalEnvDraft((current) => ({
                    ...current,
                    key: event.target.value.toUpperCase(),
                  }))
                }
                placeholder="TEAM_CONTEXT"
              />
              <FormInput
                label={tl("Valor")}
                value={localEnvDraft.value}
                onChange={(event) =>
                  setLocalEnvDraft((current) => ({
                    ...current,
                    value: event.target.value,
                  }))
                }
                placeholder={tl("Ex.: squad-platform")}
              />
              <div className="flex items-end gap-2">
                <AsyncActionButton
                  type="button"
                  size="sm"
                  onClick={handleSaveLocalEnv}
                >
                  {editingEnvKey ? tl("Atualizar") : tl("Adicionar")}
                </AsyncActionButton>
                {editingEnvKey ? (
                  <AsyncActionButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={handleCancelLocalEnv}
                  >
                    {tl("Cancelar")}
                  </AsyncActionButton>
                ) : null}
              </div>
            </div>
          </ResourceListCard>

          {localEnvEntries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
              {tl("Nenhuma variável local cadastrada para este agente.")}
            </div>
          ) : (
            <div className="space-y-2.5">
              {localEnvEntries.map((entry) => (
                <div
                  key={entry.key}
                  className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm text-[var(--text-primary)]">{entry.key}</span>
                        <ScopePill label={tl("Local ao agente")} tone="accent" />
                      </div>
                      <div className="mt-2 rounded-lg bg-[rgba(255,255,255,0.025)] px-3 py-2 font-mono text-xs break-all text-[var(--text-secondary)]">
                        {entry.value}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
                        onClick={() => handleEditLocalEnv(entry.key, entry.value)}
                      >
                        <Pencil size={14} />
                        {tl("Editar")}
                      </button>
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-lg border border-[rgba(255,110,110,0.18)] px-3 py-2 text-sm text-[var(--tone-danger-text)] transition-colors hover:bg-[rgba(255,110,110,0.08)]"
                        onClick={() => handleDeleteLocalEnv(entry.key)}
                      >
                        <Trash2 size={14} />
                        {tl("Remover")}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </PolicyCard>
      </section>

      <section className="flex flex-col gap-6 border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Segredos locais do agente")}
          description={tl("Credenciais exclusivas deste agente. Permanecem mascaradas e não entram em grants de outros bots.")}
          icon={KeyRound}
        >
          <ResourceListCard
            title={editingLocalSecretKey ? tl("Atualizar segredo local") : tl("Novo segredo local")}
            description={tl("Use segredos locais quando a credencial não deve ficar disponível para outros agentes.")}
            countLabel={tl("{{count}} item(ns)", { count: localSecrets.length })}
          >
            <div className="grid gap-3 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_auto]">
              <FormInput
                label={tl("Nome da chave")}
                value={state.secretKey}
                onChange={(event) => updateField("secretKey", event.target.value.toUpperCase())}
                placeholder={tl("JIRA_API_TOKEN")}
                disabled={Boolean(editingLocalSecretKey)}
              />
              <div className="flex flex-col gap-1.5">
                <span className="eyebrow">{editingLocalSecretKey ? tl("Novo valor") : tl("Valor")}</span>
                <SecretInput
                  value={state.secretValue}
                  onChange={(event) => updateField("secretValue", event.target.value)}
                  placeholder={
                    editingLocalSecretKey ? tl("Digite um novo valor para substituir") : tl("Cole o segredo aqui")
                  }
                />
              </div>
              <div className="flex items-end gap-2">
                <AsyncActionButton
                  type="button"
                  size="sm"
                  loading={isPending("save-secret")}
                  loadingLabel={tl("Salvando")}
                  onClick={handleSaveLocalSecret}
                >
                  {editingLocalSecretKey ? tl("Atualizar") : tl("Salvar")}
                </AsyncActionButton>
                {editingLocalSecretKey ? (
                  <AsyncActionButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={resetLocalSecretEditor}
                  >
                    {tl("Cancelar")}
                  </AsyncActionButton>
                ) : null}
              </div>
            </div>
            {editingLocalSecretKey ? (
              <div className="mt-3 rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.018)] px-3 py-2 text-xs leading-relaxed text-[var(--text-quaternary)]">
                {tl("Você está substituindo o valor de")}{" "}
                <span className="font-mono text-[var(--text-secondary)]">{editingLocalSecretKey}</span>.
                {" "}
                {tl("O valor atual continua mascarado e não é exibido pela interface.")}
              </div>
            ) : null}
          </ResourceListCard>

          {localSecrets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-4 text-sm text-[var(--text-quaternary)]">
              {tl("Nenhum segredo local cadastrado para este agente.")}
            </div>
          ) : (
            <div className="space-y-2.5">
              {localSecrets.map((secret) => {
                const secretKey = String(secret.secret_key || "SECRET");
                return (
                  <div
                    key={secretKey}
                    className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-4 py-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm font-mono text-[var(--text-primary)]">{secretKey}</div>
                          <ScopePill label={tl("Segredo local")} tone="accent" />
                        </div>
                        <div className="mt-2">
                          <MaskedSecretPreview preview={String(secret.preview || tl("mascarado"))} />
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <AsyncActionButton
                          type="button"
                          variant="secondary"
                          size="sm"
                          className="inline-flex items-center gap-2 rounded-lg"
                          onClick={() => beginEditLocalSecret(secretKey)}
                          icon={Pencil}
                        >
                          {tl("Editar")}
                        </AsyncActionButton>
                        <AsyncActionButton
                          type="button"
                          variant="danger"
                          size="sm"
                          className="inline-flex items-center gap-2 rounded-lg"
                          loading={isPending(`delete-secret:${secretKey}`)}
                          loadingLabel={tl("Removendo")}
                          onClick={() => handleDeleteLocalSecret(secretKey)}
                          aria-label={tl("Remover {{key}}", { key: secretKey })}
                          icon={Trash2}
                        >
                          {tl("Remover")}
                        </AsyncActionButton>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </PolicyCard>
      </section>

    </div>
  );
}
