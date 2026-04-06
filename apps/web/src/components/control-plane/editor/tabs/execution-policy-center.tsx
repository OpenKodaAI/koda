"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BadgeInfo,
  Layers3,
  Plus,
  RefreshCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Wand2,
} from "lucide-react";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { FormInput, FormSelect } from "@/components/control-plane/shared/form-field";
import { ListEditorField } from "@/components/control-plane/shared/list-editor-field";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { requestJson } from "@/lib/http-client";
import {
  parseExecutionPolicy,
  serializeExecutionPolicy,
  type ExecutionPolicyData,
} from "@/lib/policy-serializers";
import { cn } from "@/lib/utils";
import type {
  ControlPlaneExecutionPolicyCatalog,
  ControlPlaneExecutionPolicyCatalogAction,
  ControlPlaneExecutionPolicyEvaluation,
} from "@/lib/control-plane";

type CatalogActionView = ControlPlaneExecutionPolicyCatalogAction & {
  action_id: string;
  title: string;
  description: string;
  default_decision: string;
  default_reason_code: string;
  preview_required_default: boolean;
  approval_scope_default: string;
  source_kind: "catalog" | "derived";
};

type SimulatorEnvelope = Record<string, unknown> & {
  tool_id?: string;
  integration_id?: string;
  action_id?: string;
  server_key?: string;
  transport?: string;
  access_level?: string;
  risk_class?: string;
  effect_tags?: string[];
  resource_method?: string;
  task_kind?: string;
  domain?: string;
  path?: string;
  db_env?: string;
  private_network?: boolean;
  uses_secrets?: boolean;
  bulk_operation?: boolean;
  external_side_effect?: boolean;
};

function isNonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function compactObject<T extends Record<string, unknown>>(value: T): Partial<T> {
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (item === undefined || item === null || item === "") continue;
    if (Array.isArray(item) && item.length === 0) continue;
    if (typeof item === "object" && !Array.isArray(item) && Object.keys(item as Record<string, unknown>).length === 0) {
      continue;
    }
    result[key] = item;
  }
  return result as Partial<T>;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function joinList(items: string[]) {
  return items.join(", ");
}

function buildActionViews(
  catalog?: ControlPlaneExecutionPolicyCatalog | null,
): CatalogActionView[] {
  const actions = Array.isArray(catalog?.actions) ? catalog.actions : [];
  if (actions.length > 0) {
    return actions.map((action, index) => {
      const actionId = asString(action.action_id, asString(action.tool_id, `action_${index + 1}`));
      return {
        ...action,
        action_id: actionId,
        title: asString(action.title, actionId),
        description: asString(action.description),
        default_decision: asString(action.default_decision, "allow"),
        default_reason_code: asString(action.default_reason_code, "catalog_action"),
        preview_required_default: Boolean(action.preview_required_default),
        approval_scope_default: asString(action.approval_scope_default, "tool_call"),
        source_kind: "catalog",
      };
    });
  }

  const tools = Array.isArray(catalog?.core_tools) ? catalog.core_tools : [];
  return tools.map((tool, index) => {
    const toolId = asString(tool.id, `tool_${index + 1}`);
    const readOnly = Boolean(tool.read_only);
    return {
      action_id: asString(tool.action_id, toolId),
      tool_id: toolId,
      title: asString(tool.title, toolId),
      description: asString(tool.description),
      transport: asString(tool.transport, "core"),
      access_level: readOnly ? "read" : "write",
      risk_class: readOnly ? "low" : "medium",
      effect_tags: asStringArray(tool.effect_tags),
      resource_method: asString(tool.resource_method, readOnly ? "read" : "write"),
      default_decision: readOnly ? "allow" : "allow_with_preview",
      default_reason_code: readOnly ? "safe_read_default" : "preview_required_default",
      preview_required_default: !readOnly,
      approval_scope_default: readOnly ? "none" : "tool_call",
      source_kind: "derived",
    };
  });
}

function buildRuleTemplate(action: CatalogActionView): ExecutionPolicyData["rules"][number] {
  const match = compactObject({
    tool_id: action.tool_id,
    integration_id: action.integration_id,
    action_id: action.action_id,
    server_key: action.server_key,
    transport: action.transport,
    access_level: action.access_level,
    risk_class: action.risk_class,
    effect_tags: action.effect_tags && action.effect_tags.length > 0 ? action.effect_tags : undefined,
  }) as Record<string, unknown>;

  return {
    name: `${action.action_id}_rule`,
    priority: 50,
    match,
    decision: action.preview_required_default ? "allow_with_preview" : action.default_decision || "allow",
    reason: action.default_reason_code || "catalog_action",
    preview_fields: ["tool_id", "action_id"],
    approval_scope_kind: action.approval_scope_default || "tool_call",
    approval_ttl_seconds: 300,
  };
}

function buildSimulatorFromAction(action?: CatalogActionView | null): SimulatorEnvelope {
  if (!action) {
    return {
      tool_id: "",
      integration_id: "",
      action_id: "",
      access_level: "read",
      risk_class: "low",
      effect_tags: [],
      transport: "core",
      private_network: false,
      uses_secrets: false,
      bulk_operation: false,
      external_side_effect: false,
    };
  }

  return {
    tool_id: action.tool_id || "",
    integration_id: action.integration_id || "",
    action_id: action.action_id || "",
    server_key: action.server_key || "",
    transport: action.transport || "core",
    access_level: action.access_level || "read",
    risk_class: action.risk_class || "low",
    effect_tags: action.effect_tags ?? [],
    resource_method: action.resource_method || "",
    private_network: Boolean((action as Record<string, unknown>).private_network),
    uses_secrets: Boolean((action as Record<string, unknown>).uses_secrets),
    bulk_operation: Boolean((action as Record<string, unknown>).bulk_operation),
    external_side_effect: Boolean((action as Record<string, unknown>).external_side_effect),
  };
}

function makeRuleMatch(rule: ExecutionPolicyData["rules"][number]) {
  return (rule.match ?? {}) as Record<string, unknown>;
}

function updateRule(
  policy: ExecutionPolicyData,
  index: number,
  nextRule: ExecutionPolicyData["rules"][number],
): ExecutionPolicyData {
  const rules = policy.rules.slice();
  rules[index] = nextRule;
  return { ...policy, rules };
}

function removeRule(policy: ExecutionPolicyData, index: number): ExecutionPolicyData {
  return { ...policy, rules: policy.rules.filter((_, itemIndex) => itemIndex !== index) };
}

function patchRuleMatch(
  rule: ExecutionPolicyData["rules"][number],
  key: string,
  value: unknown,
) {
  const nextMatch = { ...(rule.match ?? {}) } as Record<string, unknown>;
  if (value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
    delete nextMatch[key];
  } else {
    nextMatch[key] = value;
  }
  return { ...rule, match: nextMatch };
}

function readSelectValue(value: unknown) {
  return typeof value === "boolean" ? (value ? "true" : "false") : typeof value === "string" ? value : "";
}

export function ExecutionPolicyCenter() {
  const { state, updateAgentSpecField, executionPolicyPayload } = useBotEditor();
  const { tl } = useAppI18n();
  const policy = useMemo(() => parseExecutionPolicy(state.executionPolicyJson), [state.executionPolicyJson]);
  const catalog = executionPolicyPayload?.catalog ?? null;
  const actions = useMemo(() => buildActionViews(catalog), [catalog]);
  const [actionSearch, setActionSearch] = useState("");
  const [selectedActionId, setSelectedActionId] = useState<string>("");
  const [simulator, setSimulator] = useState<SimulatorEnvelope>(() => buildSimulatorFromAction(actions[0] ?? null));
  const [evaluation, setEvaluation] = useState<ControlPlaneExecutionPolicyEvaluation | null>(null);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  useEffect(() => {
    if (actions.length === 0) {
      setSelectedActionId("");
      setSimulator(buildSimulatorFromAction(null));
      return;
    }

    const selected = actions.find((action) => action.action_id === selectedActionId) ?? actions[0];
    if (selected && selected.action_id !== selectedActionId) {
      setSelectedActionId(selected.action_id);
    }
    setSimulator(buildSimulatorFromAction(selected));
  }, [actions, selectedActionId]);

  const selectedAction = useMemo(
    () => actions.find((action) => action.action_id === selectedActionId) ?? actions[0] ?? null,
    [actions, selectedActionId],
  );

  const filteredActions = useMemo(() => {
    const term = actionSearch.trim().toLowerCase();
    if (!term) return actions;
    return actions.filter((action) => {
      const haystack = [
        action.action_id,
        action.title,
        action.description,
        action.tool_id,
        action.integration_id,
        action.access_level,
        action.risk_class,
        joinList(action.effect_tags ?? []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [actions, actionSearch]);

  const source = executionPolicyPayload?.source || policy.source || "explicit";
  const isCompiledLegacy = source === "compiled_legacy";
  const actionCount = actions.length;
  const ruleCount = policy.rules.length;

  function updatePolicy(nextPolicy: ExecutionPolicyData) {
    updateAgentSpecField("executionPolicyJson", serializeExecutionPolicy(nextPolicy));
  }

  function patchPolicy(updater: (current: ExecutionPolicyData) => ExecutionPolicyData) {
    updatePolicy(updater(policy));
  }

  function addRuleFromAction(action: CatalogActionView) {
    patchPolicy((current) => ({
      ...current,
      rules: [...current.rules, buildRuleTemplate(action)],
    }));
  }

  async function evaluatePolicy() {
    setIsEvaluating(true);
    setEvaluationError(null);
    try {
      const payload = await requestJson<ControlPlaneExecutionPolicyEvaluation>(
        `/api/control-plane/agents/${state.bot.id}/execution-policy/evaluate`,
        {
          method: "POST",
          body: JSON.stringify({
            policy,
            action: simulator,
          }),
        },
      );
      setEvaluation(payload);
    } catch (error) {
      setEvaluation(null);
      setEvaluationError(error instanceof Error ? error.message : tl("Falha ao avaliar policy."));
    } finally {
      setIsEvaluating(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PolicyCard
        title={tl("Policy Center")}
        description={tl("Editor primário de execution policy baseado no catálogo e no simulador de avaliação.")}
        icon={ShieldCheck}
        dirty={state.executionPolicyDirty}
        defaultOpen
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                <BadgeInfo size={12} />
                {tl("Source")}
                <span className="text-[var(--text-secondary)]">{source}</span>
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                <Layers3 size={12} />
                {actionCount} {tl(actionCount === 1 ? "ação" : "ações")}
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                <Sparkles size={12} />
                {ruleCount} {tl(ruleCount === 1 ? "regra" : "regras")}
              </span>
              {catalog?.version != null && (
                <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                  <SlidersHorizontal size={12} />
                  {tl("Catalogo v{{version}}", { version: catalog.version })}
                </span>
              )}
            </div>

            {isCompiledLegacy && (
              <button
                type="button"
                onClick={() => updateAgentSpecField("executionPolicyJson", state.executionPolicyJson)}
                className="button-shell button-shell--primary button-shell--sm gap-2"
              >
                <RefreshCcw size={14} />
                {tl("Migrar para policy explícita")}
              </button>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--surface-elevated)] text-[var(--text-secondary)]">
                  <Wand2 size={15} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-[var(--text-primary)]">
                    {tl("Estado da policy")}
                  </div>
                  <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                    {isCompiledLegacy
                      ? tl("A policy atual foi compilada a partir de tool_policy, autonomy_policy e resource_access_policy. Use a migração para materializar um draft explícito.")
                      : tl("A policy efetiva já está materializada e pode ser editada visualmente, simulada e salva como draft único.")}
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--surface-elevated)] text-[var(--text-secondary)]">
                  <ArrowRight size={15} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-[var(--text-primary)]">
                    {tl("Decisões disponíveis")}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(catalog?.decision_values ?? ["allow", "allow_with_preview", "require_approval", "deny"]).map((value) => (
                      <span
                        key={value}
                        className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]"
                      >
                        {value}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </PolicyCard>

      <PolicyCard
        title={tl("Catálogo de ações")}
        description={tl("Selecione uma ação governável para inspecionar regras, criar novos limites ou alimentar o simulador.")}
        icon={Layers3}
        defaultOpen
      >
        <div className="flex flex-col gap-4">
          <FormInput
            label={tl("Buscar ação")}
            value={actionSearch}
            onChange={(event) => setActionSearch(event.target.value)}
            placeholder={tl("Digite tool, action, integração ou efeito")}
          />

          <div className="grid gap-3 xl:grid-cols-2">
            {filteredActions.length > 0 ? (
              filteredActions.map((action) => {
                const selected = action.action_id === selectedActionId;
                return (
                  <div
                    key={`${action.source_kind}:${action.action_id}`}
                    className={cn(
                      "rounded-[1.15rem] border px-4 py-4 transition-colors",
                      selected
                        ? "border-[var(--border-strong)] bg-[var(--surface-elevated)]"
                        : "border-[var(--border-subtle)] bg-[var(--surface-canvas)] hover:border-[var(--border-strong)]",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedActionId(action.action_id)}
                      className="flex w-full items-start justify-between gap-3 text-left"
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-[var(--text-primary)]">
                            {action.title}
                          </span>
                          <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                            {action.source_kind}
                          </span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-sm leading-6 text-[var(--text-secondary)]">
                          {action.description || action.action_id}
                        </p>
                      </div>
                      <div className="text-[var(--text-quaternary)]">
                        <ArrowRight size={14} />
                      </div>
                    </button>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {[action.action_id, action.tool_id, action.integration_id, action.access_level, action.risk_class]
                        .filter(isNonEmpty)
                        .map((item) => (
                          <span
                            key={item}
                            className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-quaternary)]"
                          >
                            {item}
                          </span>
                        ))}
                      {(action.effect_tags ?? []).map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-quaternary)]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedActionId(action.action_id)}
                        className="button-shell button-shell--secondary button-shell--sm"
                      >
                        {tl("Usar na simulação")}
                      </button>
                      <button
                        type="button"
                        onClick={() => addRuleFromAction(action)}
                        className="button-shell button-shell--primary button-shell--sm gap-2"
                      >
                        <Plus size={14} />
                        {tl("Criar regra")}
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="rounded-[1.15rem] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-tint)] p-5 text-sm text-[var(--text-secondary)]">
                {tl("Nenhuma ação encontrada no catálogo atual.")}
              </div>
            )}
          </div>
        </div>
      </PolicyCard>

      <PolicyCard
        title={tl("Simulador de decisão")}
        description={tl("Monte um envelope, rode o evaluate endpoint e veja a decisão final antes de salvar o draft.")}
        icon={ShieldCheck}
        defaultOpen
      >
        <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="flex flex-col gap-4 rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">
                  {tl("Envelope")}
                </div>
                <p className="text-sm text-[var(--text-secondary)]">
                  {tl("Ação selecionada e overrides usados para simulação.")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSimulator(buildSimulatorFromAction(selectedAction))}
                className="button-shell button-shell--secondary button-shell--sm"
              >
                {tl("Recarregar ação")}
              </button>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <FormInput
                label={tl("tool_id")}
                value={typeof simulator.tool_id === "string" ? simulator.tool_id : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, tool_id: event.target.value }))}
                placeholder={tl("Ex: gmail.send")}
              />
              <FormInput
                label={tl("action_id")}
                value={typeof simulator.action_id === "string" ? simulator.action_id : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, action_id: event.target.value }))}
                placeholder={tl("Ex: users.messages.send")}
              />
              <FormInput
                label={tl("integration_id")}
                value={typeof simulator.integration_id === "string" ? simulator.integration_id : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, integration_id: event.target.value }))}
                placeholder={tl("Ex: gmail")}
              />
              <FormInput
                label={tl("server_key")}
                value={typeof simulator.server_key === "string" ? simulator.server_key : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, server_key: event.target.value }))}
                placeholder={tl("Ex: gmail-prod")}
              />
              <FormInput
                label={tl("domain")}
                value={typeof simulator.domain === "string" ? simulator.domain : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, domain: event.target.value }))}
                placeholder={tl("Ex: mail.google.com")}
              />
              <FormInput
                label={tl("path")}
                value={typeof simulator.path === "string" ? simulator.path : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, path: event.target.value }))}
                placeholder={tl("Ex: /v1/users/messages/send")}
              />
              <FormInput
                label={tl("db_env")}
                value={typeof simulator.db_env === "string" ? simulator.db_env : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, db_env: event.target.value }))}
                placeholder={tl("Ex: prod")}
              />
              <FormInput
                label={tl("task_kind")}
                value={typeof simulator.task_kind === "string" ? simulator.task_kind : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, task_kind: event.target.value }))}
                placeholder={tl("Ex: deploy")}
              />
              <FormSelect
                label={tl("transport")}
                value={typeof simulator.transport === "string" ? simulator.transport : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, transport: event.target.value }))}
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "core", label: "core" },
                  { value: "mcp", label: "mcp" },
                  { value: "http", label: "http" },
                  { value: "shell", label: "shell" },
                ]}
              />
              <FormSelect
                label={tl("access_level")}
                value={typeof simulator.access_level === "string" ? simulator.access_level : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, access_level: event.target.value }))}
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "read", label: "read" },
                  { value: "write", label: "write" },
                  { value: "destructive", label: "destructive" },
                  { value: "admin", label: "admin" },
                ]}
              />
              <FormSelect
                label={tl("risk_class")}
                value={typeof simulator.risk_class === "string" ? simulator.risk_class : ""}
                onChange={(event) => setSimulator((current) => ({ ...current, risk_class: event.target.value }))}
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "low", label: "low" },
                  { value: "medium", label: "medium" },
                  { value: "high", label: "high" },
                  { value: "critical", label: "critical" },
                ]}
              />
              <FormSelect
                label={tl("private_network")}
                value={readSelectValue(simulator.private_network)}
                onChange={(event) =>
                  setSimulator((current) => ({
                    ...current,
                    private_network:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  }))
                }
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "true", label: tl("Sim") },
                  { value: "false", label: tl("Não") },
                ]}
              />
              <FormSelect
                label={tl("uses_secrets")}
                value={readSelectValue(simulator.uses_secrets)}
                onChange={(event) =>
                  setSimulator((current) => ({
                    ...current,
                    uses_secrets:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  }))
                }
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "true", label: tl("Sim") },
                  { value: "false", label: tl("Não") },
                ]}
              />
              <FormSelect
                label={tl("bulk_operation")}
                value={readSelectValue(simulator.bulk_operation)}
                onChange={(event) =>
                  setSimulator((current) => ({
                    ...current,
                    bulk_operation:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  }))
                }
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "true", label: tl("Sim") },
                  { value: "false", label: tl("Não") },
                ]}
              />
              <FormSelect
                label={tl("external_side_effect")}
                value={readSelectValue(simulator.external_side_effect)}
                onChange={(event) =>
                  setSimulator((current) => ({
                    ...current,
                    external_side_effect:
                      event.target.value === ""
                        ? undefined
                        : event.target.value === "true",
                  }))
                }
                options={[
                  { value: "", label: tl("Qualquer") },
                  { value: "true", label: tl("Sim") },
                  { value: "false", label: tl("Não") },
                ]}
              />
            </div>

            <ListEditorField
              label={tl("effect_tags")}
              description={tl("Seletores por efeito usados para validar preview e approval.")}
              items={Array.isArray(simulator.effect_tags) ? simulator.effect_tags : []}
              onChange={(items) => setSimulator((current) => ({ ...current, effect_tags: items }))}
              placeholder={tl("Ex: external_communication")}
            />

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={evaluatePolicy}
                disabled={isEvaluating}
                className="button-shell button-shell--primary button-shell--sm gap-2"
              >
                {isEvaluating ? (
                  <RefreshCcw size={14} className="animate-spin" />
                ) : (
                  <ShieldCheck size={14} />
                )}
                {tl("Avaliar policy")}
              </button>
              {selectedAction && (
                <button
                  type="button"
                  onClick={() => addRuleFromAction(selectedAction)}
                  className="button-shell button-shell--secondary button-shell--sm gap-2"
                >
                  <Plus size={14} />
                  {tl("Criar regra desta ação")}
                </button>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
                <BadgeInfo size={15} />
                {tl("Resultado")}
              </div>
              {evaluationError ? (
                <p className="mt-3 text-sm leading-6 text-[var(--tone-danger-text)]">
                  {evaluationError}
                </p>
              ) : evaluation ? (
                <div className="mt-3 flex flex-col gap-3">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                        {tl("Decision")}
                      </div>
                      <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                        {asString(evaluation.evaluation.decision, tl("Sem decisão"))}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                        {tl("Reason")}
                      </div>
                      <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                        {asString(evaluation.evaluation.reason_code, tl("Sem motivo"))}
                      </div>
                    </div>
                  </div>
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                      {tl("Matched selector")}
                    </div>
                    <pre className="mt-2 overflow-auto text-xs leading-6 text-[var(--text-secondary)]">
                      {JSON.stringify(evaluation.evaluation.matched_selector ?? {}, null, 2)}
                    </pre>
                  </div>
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                      {tl("Approval scope")}
                    </div>
                    <pre className="mt-2 overflow-auto text-xs leading-6 text-[var(--text-secondary)]">
                      {JSON.stringify(evaluation.evaluation.approval_scope ?? {}, null, 2)}
                    </pre>
                  </div>
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                      {tl("Preview text")}
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--text-secondary)]">
                      {typeof evaluation.evaluation.preview_text === "string" &&
                      evaluation.evaluation.preview_text.trim()
                        ? evaluation.evaluation.preview_text
                        : tl("O backend ainda não retornou preview_text para esta ação.")}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
                      {tl("Audit payload")}
                    </div>
                    <pre className="mt-2 overflow-auto text-xs leading-6 text-[var(--text-secondary)]">
                      {JSON.stringify(evaluation.evaluation.audit_payload ?? {}, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                  {tl("Execute uma avaliação para inspecionar a decisão, preview e auditoria.")}
                </p>
              )}
            </div>

            <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
              <div className="text-sm font-medium text-[var(--text-primary)]">
                {tl("Ação selecionada")}
              </div>
              {selectedAction ? (
                <div className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
                  <p>{selectedAction.title}</p>
                  <p className="text-[var(--text-quaternary)]">{selectedAction.description || selectedAction.action_id}</p>
                  <div className="flex flex-wrap gap-2">
                    {[selectedAction.action_id, selectedAction.tool_id, selectedAction.integration_id, selectedAction.default_decision, selectedAction.approval_scope_default]
                      .filter(isNonEmpty)
                      .map((item) => (
                        <span
                          key={item}
                          className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-quaternary)]"
                        >
                          {item}
                        </span>
                      ))}
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-sm text-[var(--text-secondary)]">
                  {tl("Selecione uma ação do catálogo para usar na simulação.")}
                </p>
              )}
            </div>
          </div>
        </div>
      </PolicyCard>

      <PolicyCard
        title={tl("Regras da policy")}
        description={tl("Ajuste as regras materializadas do draft único. O JSON bruto continua apenas no developer mode.")}
        icon={Sparkles}
        defaultOpen
        dirty={state.executionPolicyDirty}
      >
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm text-[var(--text-secondary)]">
              {tl("Cada regra pode mirar tool, integration, action, domínio, path, DB env e sinais de risco.")}
            </div>
            <button
              type="button"
              onClick={() =>
                patchPolicy((current) => ({
                  ...current,
                  rules: [
                    ...current.rules,
                    {
                      name: `rule_${current.rules.length + 1}`,
                      priority: 0,
                      match: {},
                      decision: "require_approval",
                      approval_scope_kind: "tool_call",
                      approval_ttl_seconds: 300,
                    },
                  ],
                }))
              }
              className="button-shell button-shell--primary button-shell--sm gap-2"
            >
              <Plus size={14} />
              {tl("Adicionar regra")}
            </button>
          </div>

          {policy.rules.length > 0 ? (
            <div className="grid gap-3">
              {policy.rules.map((rule, index) => {
                const match = makeRuleMatch(rule);
                return (
                  <div
                    key={`${rule.name || "rule"}-${index}`}
                    className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-[var(--text-primary)]">
                          {tl("Regra {{index}}", { index: index + 1 })}
                        </div>
                        <p className="text-sm text-[var(--text-secondary)]">
                          {tl("As regras são avaliadas no runtime central e passam pelo human factor quando necessário.")}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => patchPolicy((current) => removeRule(current, index))}
                        className="button-shell button-shell--secondary button-shell--sm"
                      >
                        {tl("Remover")}
                      </button>
                    </div>

                    <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                      <FormInput
                        label={tl("Nome")}
                        value={asString(rule.name, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, {
                              ...rule,
                              name: event.target.value,
                            }),
                          )
                        }
                        placeholder={tl("Ex: allow_gmail_send")}
                      />
                      <FormInput
                        label={tl("Prioridade")}
                        type="number"
                        value={String(rule.priority ?? 0)}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, {
                              ...rule,
                              priority: Number(event.target.value || 0),
                            }),
                          )
                        }
                      />
                      <FormSelect
                        label={tl("Decision")}
                        value={asString(rule.decision, "require_approval")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, {
                              ...rule,
                              decision: event.target.value,
                            }),
                          )
                        }
                        options={[
                          { value: "allow", label: "allow" },
                          { value: "allow_with_preview", label: "allow_with_preview" },
                          { value: "require_approval", label: "require_approval" },
                          { value: "deny", label: "deny" },
                        ]}
                      />
                      <FormInput
                        label={tl("Motivo")}
                        value={asString(rule.reason, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, {
                              ...rule,
                              reason: event.target.value,
                            }),
                          )
                        }
                        placeholder={tl("Ex: legacy_integration_deny_actions")}
                      />
                      <FormInput
                        label={tl("approval_scope_kind")}
                        value={asString(rule.approval_scope_kind, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, {
                              ...rule,
                              approval_scope_kind: event.target.value,
                            }),
                          )
                        }
                        placeholder={tl("Ex: tool_call")}
                      />
                      <FormInput
                        label={tl("approval_ttl_seconds")}
                        type="number"
                        value={rule.approval_ttl_seconds ? String(rule.approval_ttl_seconds) : ""}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, {
                              ...rule,
                              approval_ttl_seconds: event.target.value ? Number(event.target.value) : undefined,
                            }),
                          )
                        }
                        placeholder="300"
                      />
                    </div>

                    <div className="mt-4 grid gap-4 xl:grid-cols-2">
                      <FormInput
                        label={tl("tool_id")}
                        value={asString(match.tool_id, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "tool_id", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: gmail.send")}
                      />
                      <FormInput
                        label={tl("integration_id")}
                        value={asString(match.integration_id, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "integration_id", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: gmail")}
                      />
                      <FormInput
                        label={tl("action_id")}
                        value={asString(match.action_id, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "action_id", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: users.messages.send")}
                      />
                      <FormInput
                        label={tl("server_key")}
                        value={asString(match.server_key, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "server_key", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: gmail-prod")}
                      />
                      <FormInput
                        label={tl("task_kind")}
                        value={asString(match.task_kind, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "task_kind", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: deploy")}
                      />
                      <FormInput
                        label={tl("domain")}
                        value={asString(match.domain, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "domain", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: mail.google.com")}
                      />
                      <FormInput
                        label={tl("path")}
                        value={asString(match.path, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "path", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: /v1/users/messages/send")}
                      />
                      <FormInput
                        label={tl("db_env")}
                        value={asString(match.db_env, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "db_env", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: prod")}
                      />
                      <FormInput
                        label={tl("access_level")}
                        value={asString(match.access_level, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "access_level", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: write")}
                      />
                      <FormInput
                        label={tl("risk_class")}
                        value={asString(match.risk_class, "")}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "risk_class", event.target.value)),
                          )
                        }
                        placeholder={tl("Ex: high")}
                      />
                      <FormSelect
                        label={tl("private_network")}
                        value={readSelectValue(match.private_network)}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "private_network", event.target.value === "" ? undefined : event.target.value === "true")),
                          )
                        }
                        options={[
                          { value: "", label: tl("Qualquer") },
                          { value: "true", label: tl("Sim") },
                          { value: "false", label: tl("Não") },
                        ]}
                      />
                      <FormSelect
                        label={tl("uses_secrets")}
                        value={readSelectValue(match.uses_secrets)}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "uses_secrets", event.target.value === "" ? undefined : event.target.value === "true")),
                          )
                        }
                        options={[
                          { value: "", label: tl("Qualquer") },
                          { value: "true", label: tl("Sim") },
                          { value: "false", label: tl("Não") },
                        ]}
                      />
                      <FormSelect
                        label={tl("bulk_operation")}
                        value={readSelectValue(match.bulk_operation)}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "bulk_operation", event.target.value === "" ? undefined : event.target.value === "true")),
                          )
                        }
                        options={[
                          { value: "", label: tl("Qualquer") },
                          { value: "true", label: tl("Sim") },
                          { value: "false", label: tl("Não") },
                        ]}
                      />
                      <FormSelect
                        label={tl("external_side_effect")}
                        value={readSelectValue(match.external_side_effect)}
                        onChange={(event) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "external_side_effect", event.target.value === "" ? undefined : event.target.value === "true")),
                          )
                        }
                        options={[
                          { value: "", label: tl("Qualquer") },
                          { value: "true", label: tl("Sim") },
                          { value: "false", label: tl("Não") },
                        ]}
                      />
                    </div>

                    <div className="mt-4 grid gap-4 xl:grid-cols-2">
                      <ListEditorField
                        label={tl("effect_tags")}
                        items={asStringArray(match.effect_tags)}
                        onChange={(items) =>
                          patchPolicy((current) =>
                            updateRule(current, index, patchRuleMatch(rule, "effect_tags", items)),
                          )
                        }
                        placeholder={tl("Ex: external_communication")}
                      />
                      <ListEditorField
                        label={tl("preview_fields")}
                        items={asStringArray(rule.preview_fields)}
                        onChange={(items) =>
                          patchPolicy((current) =>
                            updateRule(current, index, { ...rule, preview_fields: items }),
                          )
                        }
                        placeholder={tl("Ex: matched_selector")}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-[1.15rem] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-tint)] p-5 text-sm text-[var(--text-secondary)]">
              {tl("Nenhuma regra materializada ainda. Adicione uma regra a partir do catálogo ou crie uma do zero.")}
            </div>
          )}
        </div>
      </PolicyCard>
    </div>
  );
}
