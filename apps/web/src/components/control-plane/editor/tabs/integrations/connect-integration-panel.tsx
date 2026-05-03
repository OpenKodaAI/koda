"use client";

/**
 * ConnectIntegrationPanel — inline connection UI rendered inside the
 * integration detail view when the integration is not yet connected.
 *
 * Always renders a consistent body regardless of the integration's
 * connection profile so the user is never staring at a blank panel.
 *
 * Submission flows:
 *   - OAuth: parent renders the "Conectar" button and dispatches the
 *     popup itself; this panel just shows the form fields (if any) and
 *     the JSON advanced toggle.
 *   - Form / no-creds: parent gets a ref handle (`submit()`) and calls
 *     it from the header CTA. This avoids the fragile `<button form="id">`
 *     attribute pattern in React.
 *   - JSON paste: handled inline via the "Aplicar" button.
 */

import { forwardRef, useImperativeHandle, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Loader2 } from "lucide-react";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { SecretInput } from "@/components/ui/secret-controls";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { JsonEditor } from "@/components/ui/json-editor";
import type { AgentIntegrationEntry } from "@/hooks/use-agent-integration-permissions";
import type { ConnectionField, McpOAuthStatus } from "@/lib/control-plane";

/*  Types                                                              */

export type ConnectIntegrationPanelProps = {
  entry: AgentIntegrationEntry;
  oauthStatus?: McpOAuthStatus;
  onSubmitForm: (envValues: Record<string, string>) => Promise<void>;
  onSubmitJson?: (rawJson: string) => Promise<void>;
};

export type ConnectIntegrationPanelHandle = {
  /** Imperative submit invoked by the parent's "Conectar" CTA. */
  submit: () => void;
};

type FormState = Record<string, { value: string; clear: boolean }>;

/**
 * Build a Claude Desktop / Cursor-compatible `mcpServers` snippet pre-filled
 * with the integration's command, args, transport URL and env keys. Env values
 * are emitted as placeholders so users see the exact shape they need to paste
 * back. Headers are included for HTTP-SSE servers that declare them.
 */
function buildMcpServerJsonTemplate(
  entry: AgentIntegrationEntry,
): string {
  const server = entry.mcpServer;
  const command = (server?.command && server.command.length > 0
    ? server.command
    : ["npx", "-y", entry.key]) as string[];

  const envSchema = server?.env_schema ?? [];
  const envObj: Record<string, string> = {};
  for (const field of envSchema) {
    envObj[field.key] = `<${field.label || field.key}>`;
  }
  for (const profileField of entry.connectionProfile?.fields ?? []) {
    if (envObj[profileField.key] === undefined) {
      envObj[profileField.key] = `<${profileField.label || profileField.key}>`;
    }
  }

  const headersSchema = server?.headers_schema ?? [];
  const headersObj: Record<string, string> = {};
  for (const field of headersSchema) {
    headersObj[field.key] = `<${field.label || field.key}>`;
  }

  const config: Record<string, unknown> = {
    command: command[0] ?? "npx",
    args: command.slice(1),
  };
  if (Object.keys(envObj).length > 0) config.env = envObj;
  if (server?.transport_type === "http_sse" && server?.remote_url) {
    config.url = server.remote_url;
  }
  if (Object.keys(headersObj).length > 0) config.headers = headersObj;

  return JSON.stringify({ mcpServers: { [entry.key]: config } }, null, 2);
}

/*  Component                                                          */

export const ConnectIntegrationPanel = forwardRef<
  ConnectIntegrationPanelHandle,
  ConnectIntegrationPanelProps
>(function ConnectIntegrationPanel(
  { entry, oauthStatus, onSubmitForm, onSubmitJson },
  ref,
) {
  const { tl } = useAppI18n();

  const profile = useMemo(
    () => entry.connectionProfile ?? { strategy: "none" as const },
    [entry.connectionProfile],
  );
  const oauthSupported = Boolean(entry.oauth_supported);

  const allFields = useMemo<ConnectionField[]>(() => {
    return [
      ...(profile.fields ?? []),
      ...(profile.scope_fields ?? []),
      ...(profile.read_only_toggle ? [profile.read_only_toggle] : []),
      ...(profile.path_argument ? [profile.path_argument] : []),
    ];
  }, [profile]);

  const requiresFields = allFields.length > 0;
  const isOAuthOnly = profile.strategy === "oauth_only";
  const isNoneStrategy =
    profile.strategy === "none" ||
    profile.strategy === "custom_stdio" ||
    profile.strategy === "custom_http";

  const [showAdvanced, setShowAdvanced] = useState(!oauthSupported && requiresFields);
  const [showJson, setShowJson] = useState(false);
  const [formState, setFormState] = useState<FormState>(() => {
    const initial: FormState = {};
    for (const field of allFields) initial[field.key] = { value: "", clear: false };
    return initial;
  });
  const jsonTemplate = useMemo(() => buildMcpServerJsonTemplate(entry), [entry]);
  const [jsonRaw, setJsonRaw] = useState(jsonTemplate);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const docsUrl = entry.mcpServer?.documentation_url ?? null;

  const handleFieldChange = (key: string) => (value: string) =>
    setFormState((prev) => ({ ...prev, [key]: { value, clear: false } }));

  const validateRequired = (): string | null => {
    for (const field of allFields) {
      if (field.required === false) continue;
      const state = formState[field.key];
      if (!state || !state.value.trim()) {
        return tl("Preencha {{label}}.", { label: field.label || field.key });
      }
    }
    return null;
  };

  const handleSubmitForm = async () => {
    setError(null);
    if (requiresFields) {
      const missing = validateRequired();
      if (missing) {
        setError(missing);
        return;
      }
    }
    setSubmitting(true);
    try {
      const envValues: Record<string, string> = {};
      for (const [key, state] of Object.entries(formState)) {
        if (state.value.trim()) envValues[key] = state.value;
      }
      await onSubmitForm(envValues);
    } catch (err) {
      setError(err instanceof Error ? err.message : tl("Falha ao conectar."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitJson = async () => {
    if (!onSubmitJson) return;
    setError(null);
    setSubmitting(true);
    try {
      await onSubmitJson(jsonRaw);
    } catch (err) {
      setError(err instanceof Error ? err.message : tl("Falha ao importar JSON."));
    } finally {
      setSubmitting(false);
    }
  };

  // Expose imperative submit so the page-level "Conectar" button can drive
  // the panel without relying on the `<button form="id">` HTML attribute,
  // which has been flaky inside React-portaled trees.
  useImperativeHandle(ref, () => ({
    submit: () => {
      void handleSubmitForm();
    },
  }));

  // ---------- Status copy: every state has a clear lead ----------
  const statusMessage = oauthSupported
    ? requiresFields
      ? tl("Use o botão Conectar acima para autorizar via OAuth, ou preencha credenciais manuais abaixo.")
      : tl("Use o botão Conectar acima para autorizar via OAuth.")
    : isOAuthOnly
      ? tl("Esta integração só conecta via OAuth — botão Conectar acima.")
      : isNoneStrategy && !requiresFields
        ? tl("Esta integração não requer credenciais. Clique em Conectar acima para iniciar e descobrir as capacidades.")
        : tl("Preencha os campos abaixo e clique em Conectar acima.");

  return (
    <div className="flex flex-col gap-3">
      {/* Always-on status copy so the body is never blank. */}
      <p className="text-xs leading-5 text-[var(--text-tertiary)]">{statusMessage}</p>

      {oauthStatus?.last_error ? (
        <p className="text-xs font-medium text-[var(--tone-danger-dot)]">{oauthStatus.last_error}</p>
      ) : null}

      {/* Manual form fields — collapsed under "Credenciais manuais" when OAuth is preferred */}
      {requiresFields ? (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-soft)]">
          {oauthSupported ? (
            <button
              type="button"
              onClick={() => setShowAdvanced((prev) => !prev)}
              className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
            >
              <span>{tl("Credenciais manuais")}</span>
              {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          ) : null}
          {(showAdvanced || !oauthSupported) && (
            <div className="flex flex-col gap-3 px-4 py-4">
              {allFields.map((field) => (
                <FieldRow
                  key={field.key}
                  field={field}
                  state={formState[field.key] ?? { value: "", clear: false }}
                  onChange={handleFieldChange(field.key)}
                />
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* JSON paste advanced — collapsed by default */}
      {onSubmitJson ? (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--panel-soft)]">
          <button
            type="button"
            onClick={() => setShowJson((prev) => !prev)}
            className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
          >
            <span>{tl("JSON")}</span>
            {showJson ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {showJson ? (
            <div className="flex flex-col gap-3 px-4 py-4">
              <JsonEditor
                value={jsonRaw}
                onChange={setJsonRaw}
                rows={12}
                ariaLabel="JSON"
              />
              <button
                type="button"
                onClick={handleSubmitJson}
                disabled={submitting || !jsonRaw.trim()}
                className="inline-flex h-9 items-center justify-center gap-2 self-start rounded-lg border border-[var(--border-subtle)] px-4 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-60"
              >
                {submitting ? <Loader2 size={13} className="animate-spin" /> : null}
                {tl("Aplicar")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? <p className="text-xs font-medium text-[var(--tone-danger-dot)]">{error}</p> : null}

      {docsUrl ? (
        <a
          href={docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 self-start text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
        >
          <ExternalLink size={11} />
          {tl("Documentação")}
        </a>
      ) : null}
    </div>
  );
});

/*  Internals                                                          */

function FieldRow({
  field,
  state,
  onChange,
}: {
  field: ConnectionField;
  state: { value: string; clear: boolean };
  onChange: (value: string) => void;
}) {
  const { tl } = useAppI18n();
  const isPassword = field.input_type === "password";
  const isSwitch = field.input_type === "switch";
  const isTextarea = field.input_type === "textarea";

  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-[var(--text-secondary)]">{field.label}</span>
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
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.help ?? ""}
        />
      ) : isTextarea ? (
        <Textarea
          rows={4}
          className="min-h-[5rem]"
          value={state.value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.help ?? ""}
        />
      ) : (
        <Input
          sizeVariant="sm"
          type="text"
          value={state.value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.help ?? ""}
        />
      )}
    </label>
  );
}
