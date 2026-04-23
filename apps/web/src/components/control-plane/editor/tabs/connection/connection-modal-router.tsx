"use client";

/**
 * ConnectionModalRouter
 *
 * Per-integration connect modal. Picks the right sub-form based on the
 * integration's `ConnectionProfile.strategy` declared in the catalog.
 *
 * Handles both core integrations (Jira, AWS, gh, …) and MCP servers
 * (Supabase, Slack, Obsidian, …) in one component so the user experience
 * is consistent — shared header/footer shell, integration-aware body.
 *
 * See docs/ai/integrations/README.md for the strategy taxonomy.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Lock,
  Loader2,
  Settings2,
  Trash2,
  X,
  XCircle,
} from "lucide-react";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { SecretInput } from "@/components/ui/secret-controls";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";
import { requestJson } from "@/lib/http-client";
import { cn } from "@/lib/utils";

import type {
  AgentIntegrationEntry,
} from "@/hooks/use-agent-integration-permissions";
import type {
  ConnectionField,
  ConnectionProfile,
  McpOAuthStatus,
} from "@/lib/control-plane";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export type ConnectionModalRouterProps = {
  entry: AgentIntegrationEntry;
  agentId: string;
  onClose: () => void;
  onSaved: () => void;
  onOAuthStart?: () => Promise<void>;
  isOAuthLoading?: boolean;
  oauthStatus?: McpOAuthStatus | null;
};

type TestResult = { success: boolean; message: string } | null;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function fieldsFromProfile(profile: ConnectionProfile | null | undefined): {
  primary: ConnectionField[];
  scope: ConnectionField[];
  readOnly: ConnectionField | null;
  pathArg: ConnectionField | null;
} {
  if (!profile) return { primary: [], scope: [], readOnly: null, pathArg: null };
  return {
    primary: [...(profile.fields ?? [])],
    scope: [...(profile.scope_fields ?? [])],
    readOnly: profile.read_only_toggle ?? null,
    pathArg: profile.path_argument ?? null,
  };
}

function coreFieldPresence(
  entry: AgentIntegrationEntry,
): Map<string, { preview: string | null; present: boolean; storage: string }> {
  const map = new Map<string, { preview: string | null; present: boolean; storage: string }>();
  const existing = (entry.coreConnection?.fields ?? []) as Array<Record<string, unknown>>;
  for (const field of existing) {
    const key = String(field.key ?? "");
    if (!key) continue;
    map.set(key, {
      preview: typeof field.preview === "string" ? field.preview : null,
      present: Boolean(field.value_present),
      storage: String(field.storage ?? "env"),
    });
  }
  return map;
}

function mcpExistingEnvKeys(entry: AgentIntegrationEntry): Set<string> {
  return new Set(Object.keys(entry.mcpConnection?.env_values ?? {}));
}

/* ------------------------------------------------------------------ */
/*  ModalShell                                                         */
/* ------------------------------------------------------------------ */

type ShellProps = {
  entry: AgentIntegrationEntry;
  children: React.ReactNode;
  onClose: () => void;
  onSave: () => Promise<void>;
  onTest?: () => Promise<void>;
  canSave: boolean;
  saving: boolean;
  testing: boolean;
  testResult: TestResult;
  error: string | null;
  saveLabel?: string;
};

function ModalShell({
  entry,
  children,
  onClose,
  onSave,
  onTest,
  canSave,
  saving,
  testing,
  testResult,
  error,
  saveLabel,
}: ShellProps) {
  const { tl } = useAppI18n();
  const logo = renderIntegrationLogo(entry.logoKey, "h-7 w-7");

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  if (typeof document === "undefined") return null;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel relative w-full max-w-lg max-h-[calc(100vh-4rem)] flex flex-col border-[var(--border-strong)]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="connection-modal-title"
          data-connection-modal-router
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14">
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
                style={{ backgroundColor: `${entry.accentFrom}18` }}
              >
                {logo}
              </div>
              <div>
                <h3
                  id="connection-modal-title"
                  className="text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]"
                >
                  {tl("Conectar")} {entry.label}
                </h3>
                <p className="mt-0.5 text-sm text-[var(--text-quaternary)]">
                  {entry.tagline || entry.description || tl("Configuração desta integração")}
                </p>
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto space-y-4 px-6 py-5">
            {children}
            {error ? (
              <div className="rounded-xl border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-4 py-3 text-xs text-[var(--tone-danger-text)]">
                {error}
              </div>
            ) : null}
          </div>

          {testResult ? (
            <div
              className={cn(
                "mx-6 mb-4 flex items-center gap-2 rounded-xl border px-4 py-2.5 text-xs",
                testResult.success
                  ? "border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]"
                  : "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]",
              )}
            >
              {testResult.success ? (
                <CheckCircle2 size={13} className="shrink-0" />
              ) : (
                <XCircle size={13} className="shrink-0" />
              )}
              <span>{testResult.message}</span>
            </div>
          ) : null}

          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-6 py-4">
            <div className="flex items-center gap-1.5 text-xs text-[var(--text-quaternary)]">
              <Lock size={11} />
              <span>{tl("Credenciais criptografadas")}</span>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                {tl("Cancelar")}
              </button>
              {onTest ? (
                <button
                  type="button"
                  onClick={onTest}
                  disabled={testing || saving}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-50"
                >
                  {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {tl("Testar")}
                </button>
              ) : null}
              <AsyncActionButton
                type="button"
                onClick={onSave}
                loading={saving}
                disabled={!canSave}
                loadingLabel={tl("Salvando")}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-[var(--interactive-active-text)] transition-all"
                style={{
                  background:
                    "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                  border: "1px solid var(--interactive-active-border)",
                }}
              >
                {saveLabel ?? tl("Salvar conexão")}
              </AsyncActionButton>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}

/* ------------------------------------------------------------------ */
/*  Field renderer                                                     */
/* ------------------------------------------------------------------ */

type FieldState = {
  value: string;
  clear: boolean;
};

type FieldRowProps = {
  field: ConnectionField;
  state: FieldState;
  onChange: (value: string, clear?: boolean) => void;
  preview?: string | null;
  valuePresent?: boolean;
  isSecret?: boolean;
};

function FieldRow({
  field,
  state,
  onChange,
  valuePresent,
  isSecret,
}: FieldRowProps) {
  const { tl } = useAppI18n();
  const help = field.help;
  const isPassword = (isSecret ?? field.input_type === "password");
  const isSwitch = field.input_type === "switch";
  const isTextarea = field.input_type === "textarea";

  return (
    <label className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {field.label}
        </span>
        <span className="text-[11px] text-[var(--text-quaternary)]">
          {valuePresent
            ? tl("Já configurado; preencha para substituir.")
            : field.required === false
              ? tl("Opcional")
              : tl("Obrigatório")}
        </span>
      </div>
      {help ? (
        <span className="text-[11px] text-[var(--text-quaternary)]">{help}</span>
      ) : null}
      {valuePresent ? (
        <span className="inline-flex items-center gap-1 self-start rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--tone-success-text)]">
          {tl("Configurada")}
        </span>
      ) : null}
      {isSwitch ? (
        <label className="flex items-center gap-2 text-sm text-[var(--text-primary)]">
          <input
            type="checkbox"
            checked={state.value === "true"}
            onChange={(event) => onChange(event.target.checked ? "true" : "false")}
          />
          <span className="text-xs">{tl("Ativado")}</span>
        </label>
      ) : isPassword ? (
        <SecretInput
          value={state.value}
          onChange={(event) => onChange(event.target.value, false)}
          placeholder={
            valuePresent
              ? tl("Mantido da conexão atual")
              : tl("Digite o valor")
          }
        />
      ) : isTextarea ? (
        <textarea
          className="field-shell min-h-[6rem] px-4 py-2.5 text-sm text-[var(--text-primary)]"
          value={state.value}
          onChange={(event) => onChange(event.target.value, false)}
          placeholder={tl("Preencha o valor")}
        />
      ) : (
        <input
          type="text"
          className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
          value={state.value}
          onChange={(event) => onChange(event.target.value, false)}
          placeholder={tl("Preencha o valor")}
        />
      )}
      {valuePresent && !state.value ? (
        <button
          type="button"
          onClick={() => onChange("", !state.clear)}
          className={cn(
            "inline-flex items-center gap-2 self-start rounded-lg border px-3 py-1.5 text-xs transition-colors",
            state.clear
              ? "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]"
              : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
          )}
        >
          <Trash2 size={12} />
          {state.clear ? tl("Será removido ao salvar") : tl("Remover segredo")}
        </button>
      ) : null}
    </label>
  );
}

/* ------------------------------------------------------------------ */
/*  Save helpers                                                       */
/* ------------------------------------------------------------------ */

type FieldValues = Record<string, FieldState>;

function initFieldValues(fields: ConnectionField[]): FieldValues {
  const out: FieldValues = {};
  for (const f of fields) out[f.key] = { value: "", clear: false };
  return out;
}

function filterNonEmpty(values: FieldValues): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, state] of Object.entries(values)) {
    if (state.value.trim().length > 0) out[key] = state.value;
  }
  return out;
}

function missingRequired(
  fields: ConnectionField[],
  values: FieldValues,
  alreadyPresent: Set<string>,
): ConnectionField[] {
  return fields.filter(
    (f) =>
      f.required !== false &&
      !(values[f.key]?.value.trim().length) &&
      !alreadyPresent.has(f.key),
  );
}

async function saveMcp(params: {
  agentId: string;
  connectionKey: string;
  envValues: Record<string, string>;
  transportOverride?: string;
  urlOverride?: string;
}): Promise<void> {
  const { agentId, connectionKey, envValues, transportOverride, urlOverride } = params;
  const body: Record<string, unknown> = {
    enabled: true,
    env_values: envValues,
  };
  if (transportOverride) body.transport_override = transportOverride;
  if (urlOverride) body.url_override = urlOverride;
  await requestJson(
    `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

async function testMcp(params: {
  agentId: string;
  connectionKey: string;
  envValues: Record<string, string>;
  tl: (text: string, vars?: Record<string, string | number>) => string;
}): Promise<TestResult> {
  const { agentId, connectionKey, envValues, tl } = params;
  try {
    await saveMcp({ agentId, connectionKey, envValues });
    const result = await requestJson<{
      success?: boolean;
      tool_count?: number;
      error?: string;
    }>(
      `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}/verify`,
      { method: "POST" },
    );
    if (result.success) {
      return {
        success: true,
        message:
          tl("Conexão válida") +
          (result.tool_count ? ` (${result.tool_count} tools)` : ""),
      };
    }
    return { success: false, message: result.error || tl("Falha na conexão") };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "";
    if (msg.includes("501") || msg.includes("Not Implemented")) {
      return { success: false, message: tl("Teste não disponível") };
    }
    return { success: false, message: msg || tl("Erro ao testar conexão") };
  }
}

async function saveCore(params: {
  agentId: string;
  connectionKey: string;
  fields: FieldValues;
  authMethod?: string;
}): Promise<void> {
  const { agentId, connectionKey, fields, authMethod } = params;
  const body = {
    auth_method: authMethod ?? "api_token",
    source_origin: "agent_binding",
    allow_local_session: false,
    enabled: true,
    fields: Object.entries(fields).map(([key, state]) => ({
      key,
      value: state.value,
      clear: state.clear,
    })),
  };
  await requestJson(
    `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

/* ------------------------------------------------------------------ */
/*  The router                                                         */
/* ------------------------------------------------------------------ */

export function ConnectionModalRouter({
  entry,
  agentId,
  onClose,
  onSaved,
  onOAuthStart,
  isOAuthLoading,
  oauthStatus,
}: ConnectionModalRouterProps) {
  const { tl } = useAppI18n();
  const profile = useMemo<ConnectionProfile>(
    () => entry.connectionProfile ?? { strategy: "none" },
    [entry.connectionProfile],
  );
  const { primary, scope, readOnly, pathArg } = useMemo(
    () => fieldsFromProfile(profile),
    [profile],
  );

  const alreadyPresent = useMemo(() => {
    if (entry.kind === "mcp") return mcpExistingEnvKeys(entry);
    const map = coreFieldPresence(entry);
    const set = new Set<string>();
    for (const [key, info] of map) if (info.present) set.add(key);
    return set;
  }, [entry]);

  const [values, setValues] = useState<FieldValues>(() =>
    initFieldValues([
      ...primary,
      ...scope,
      ...(readOnly ? [readOnly] : []),
      ...(pathArg ? [pathArg] : []),
    ]),
  );

  const [showManual, setShowManual] = useState(
    profile.strategy === "oauth_preferred" && primary.length > 0,
  );
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [error, setError] = useState<string | null>(null);

  const corePresence = useMemo(() => coreFieldPresence(entry), [entry]);

  const allRenderableFields = useMemo(
    () =>
      [...primary, ...scope, ...(readOnly ? [readOnly] : []), ...(pathArg ? [pathArg] : [])],
    [primary, scope, readOnly, pathArg],
  );

  const setField = useCallback(
    (key: string) =>
      (value: string, clear = false) => {
        setValues((prev) => ({ ...prev, [key]: { value, clear } }));
      },
    [],
  );

  const missing = useMemo(
    () =>
      missingRequired(
        profile.strategy === "oauth_preferred" && !showManual ? [] : primary,
        values,
        alreadyPresent,
      ),
    [profile.strategy, primary, showManual, values, alreadyPresent],
  );

  const validate = useCallback(() => {
    if (missing.length === 0) return true;
    const labels = missing.map((f) => f.label || f.key).join(", ");
    setError(tl("Preencha os campos obrigatórios: {{fields}}.", { fields: labels }));
    return false;
  }, [missing, tl]);

  const handleSave = useCallback(async () => {
    setError(null);
    setTestResult(null);
    if (!validate()) return;
    setSaving(true);
    try {
      if (entry.kind === "mcp") {
        await saveMcp({
          agentId,
          connectionKey: entry.connectionKey,
          envValues: filterNonEmpty(values),
        });
      } else {
        await saveCore({
          agentId,
          connectionKey: entry.connectionKey,
          fields: values,
          authMethod: profile.strategy === "local_app" ? "local_session" : "api_token",
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : tl("Erro ao salvar conexão"));
    } finally {
      setSaving(false);
    }
  }, [agentId, entry, onSaved, onClose, profile.strategy, validate, values, tl]);

  const handleTest = useCallback(async () => {
    if (entry.kind !== "mcp") return;
    setError(null);
    if (!validate()) return;
    setTesting(true);
    const result = await testMcp({
      agentId,
      connectionKey: entry.connectionKey,
      envValues: filterNonEmpty(values),
      tl,
    });
    setTestResult(result);
    setTesting(false);
  }, [agentId, entry, validate, values, tl]);

  const shellOnTest = entry.kind === "mcp" ? handleTest : undefined;
  const saveLabel =
    profile.strategy === "none"
      ? tl("Ativar para este agente")
      : profile.strategy === "local_app"
        ? tl("Confirmar configuração")
        : undefined;

  // --- Sub-form renderers (inline) ---

  let body: React.ReactNode;
  switch (profile.strategy) {
    case "none":
      body = (
        <p className="text-sm text-[var(--text-tertiary)]">
          {tl("Esta integração não precisa de credenciais. Ative para permitir que o agente use as ferramentas expostas.")}
        </p>
      );
      break;

    case "local_app":
      body = (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] px-4 py-3 text-sm text-[var(--tone-info-text)]">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div className="flex flex-col gap-1">
                <span className="font-medium">
                  {tl("Depende do app local: {{app}}", {
                    app: profile.local_app_name ?? entry.label,
                  })}
                </span>
                {profile.local_app_detection_hint ? (
                  <span className="text-[12px] text-[var(--text-secondary)]">
                    {profile.local_app_detection_hint}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          {primary.length > 0 ? (
            <>
              <details className="rounded-xl border border-[var(--border-subtle)] px-4 py-3 text-sm">
                <summary className="cursor-pointer text-xs text-[var(--text-tertiary)]">
                  {tl("Fallback manual (não recomendado)")}
                </summary>
                <div className="mt-3 flex flex-col gap-3">
                  {primary.map((f) => (
                    <FieldRow
                      key={f.key}
                      field={f}
                      state={values[f.key] ?? { value: "", clear: false }}
                      onChange={setField(f.key)}
                      preview={corePresence.get(f.key)?.preview}
                      valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
                    />
                  ))}
                </div>
              </details>
            </>
          ) : null}
        </div>
      );
      break;

    case "local_path":
      body = (
        <div className="flex flex-col gap-4">
          {pathArg ? (
            <FieldRow
              field={pathArg}
              state={values[pathArg.key] ?? { value: "", clear: false }}
              onChange={setField(pathArg.key)}
              preview={alreadyPresent.has(pathArg.key) ? "" : null}
              valuePresent={alreadyPresent.has(pathArg.key)}
              isSecret={false}
            />
          ) : (
            <p className="text-sm text-[var(--text-tertiary)]">
              {tl("Nenhum caminho configurado para este servidor.")}
            </p>
          )}
          {primary.length > 0
            ? primary.map((f) => (
                <FieldRow
                  key={f.key}
                  field={f}
                  state={values[f.key] ?? { value: "", clear: false }}
                  onChange={setField(f.key)}
                  preview={corePresence.get(f.key)?.preview}
                  valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
                />
              ))
            : null}
        </div>
      );
      break;

    case "dual_token":
    case "api_key":
      body = (
        <div className="flex flex-col gap-4">
          {primary.map((f) => (
            <FieldRow
              key={f.key}
              field={f}
              state={values[f.key] ?? { value: "", clear: false }}
              onChange={setField(f.key)}
              preview={corePresence.get(f.key)?.preview}
              valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
            />
          ))}
          {scope.length > 0 ? (
            <div className="flex flex-col gap-3 rounded-xl border border-[var(--border-subtle)] px-4 py-3">
              <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                {tl("Escopo (opcional)")}
              </span>
              {scope.map((f) => (
                <FieldRow
                  key={f.key}
                  field={f}
                  state={values[f.key] ?? { value: "", clear: false }}
                  onChange={setField(f.key)}
                  preview={corePresence.get(f.key)?.preview}
                  valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
                />
              ))}
            </div>
          ) : null}
        </div>
      );
      break;

    case "connection_string":
      body = (
        <div className="flex flex-col gap-4">
          {primary.map((f) => (
            <FieldRow
              key={f.key}
              field={f}
              state={values[f.key] ?? { value: "", clear: false }}
              onChange={setField(f.key)}
              preview={corePresence.get(f.key)?.preview}
              valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
            />
          ))}
          {readOnly ? (
            <div className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3">
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  {readOnly.label}
                </span>
                {readOnly.help ? (
                  <span className="text-[11px] text-[var(--text-quaternary)]">
                    {readOnly.help}
                  </span>
                ) : null}
              </div>
              <input
                type="checkbox"
                checked={values[readOnly.key]?.value === "true"}
                onChange={(event) =>
                  setField(readOnly.key)(event.target.checked ? "true" : "false", false)
                }
              />
            </div>
          ) : null}
        </div>
      );
      break;

    case "oauth_only":
    case "oauth_preferred": {
      const providerLabel = profile.oauth_provider
        ? profile.oauth_provider.charAt(0).toUpperCase() + profile.oauth_provider.slice(1)
        : entry.label;
      body = (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-4">
            <div className="flex flex-col gap-3">
              <span className="text-xs text-[var(--text-tertiary)]">
                {profile.strategy === "oauth_only"
                  ? tl("Este provedor só aceita OAuth.")
                  : tl("Recomendado usar OAuth; o fallback manual fica disponível abaixo.")}
              </span>
              {oauthStatus?.connected ? (
                <div className="flex items-center gap-2 rounded-lg border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-3 py-2 text-xs text-[var(--tone-success-text)]">
                  <CheckCircle2 size={13} />
                  <span>
                    {tl("Conectado como {{account}}", {
                      account: oauthStatus.account_label ?? providerLabel,
                    })}
                  </span>
                </div>
              ) : null}
              <button
                type="button"
                onClick={onOAuthStart}
                disabled={!onOAuthStart || isOAuthLoading}
                className={cn(
                  "inline-flex items-center justify-center gap-2 rounded-xl",
                  "bg-[var(--surface-elevated)] border border-[var(--border-strong)]",
                  "px-4 py-2 text-sm font-medium text-[var(--text-primary)]",
                  "transition-colors hover:bg-[var(--surface-hover-strong)]",
                  (isOAuthLoading || !onOAuthStart) && "opacity-60 cursor-wait",
                )}
              >
                {isOAuthLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                {oauthStatus?.connected
                  ? tl("Reconectar via {{provider}}", { provider: providerLabel })
                  : tl("Conectar com {{provider}}", { provider: providerLabel })}
              </button>
            </div>
          </div>

          {profile.strategy === "oauth_preferred" && primary.length > 0 ? (
            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={() => setShowManual((v) => !v)}
                className="inline-flex items-center gap-1.5 self-start text-xs text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)]"
              >
                <Settings2 size={12} />
                {showManual
                  ? tl("Ocultar fallback manual")
                  : tl("Configurar manualmente")}
              </button>
              {showManual ? (
                <div className="flex flex-col gap-3 rounded-xl border border-[var(--border-subtle)] px-4 py-3">
                  {primary.map((f) => (
                    <FieldRow
                      key={f.key}
                      field={f}
                      state={values[f.key] ?? { value: "", clear: false }}
                      onChange={setField(f.key)}
                      preview={corePresence.get(f.key)?.preview}
                      valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {profile.strategy === "oauth_only" && primary.length > 0 ? (
            <details className="rounded-xl border border-[var(--border-subtle)] px-4 py-3 text-sm">
              <summary className="cursor-pointer text-xs text-[var(--text-tertiary)]">
                {tl("Fallback manual (legado)")}
              </summary>
              <div className="mt-3 flex flex-col gap-3">
                {primary.map((f) => (
                  <FieldRow
                    key={f.key}
                    field={f}
                    state={values[f.key] ?? { value: "", clear: false }}
                    onChange={setField(f.key)}
                    preview={corePresence.get(f.key)?.preview}
                    valuePresent={corePresence.get(f.key)?.present || alreadyPresent.has(f.key)}
                  />
                ))}
              </div>
            </details>
          ) : null}
        </div>
      );
      break;
    }

    default:
      body = (
        <p className="text-sm text-[var(--text-tertiary)]">
          {tl("Strategy \"{{s}}\" não implementada.", { s: profile.strategy })}
        </p>
      );
  }

  // For OAuth-only strategies with no manual fallback, the save button
  // is unnecessary; but we keep it so the user can persist the "enabled"
  // flag after OAuth completes. canSave is always true — OAuth fills fields
  // out-of-band.
  const canSave =
    profile.strategy === "none" ||
    profile.strategy === "local_app" ||
    profile.strategy === "oauth_only" ||
    (profile.strategy === "oauth_preferred" && !showManual) ||
    missing.length === 0;

  // Silence unused-variable warnings from the big schema types; TS keeps
  // these for future sub-forms.
  void allRenderableFields;

  return (
    <ModalShell
      entry={entry}
      onClose={onClose}
      onSave={handleSave}
      onTest={shellOnTest}
      canSave={canSave}
      saving={saving}
      testing={testing}
      testResult={testResult}
      error={error}
      saveLabel={saveLabel}
    >
      {body}
    </ModalShell>
  );
}
