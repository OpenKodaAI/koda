"use client";

import { translate } from "@/lib/i18n";
/**
 * McpCustomServerModal — register a custom MCP server (system-wide or
 * per-agent), either via form fields or by pasting a Claude Desktop /
 * cursor.config.json compatible JSON snippet.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Plus, Trash2, X } from "lucide-react";

import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { EMPTY_MCP_SERVERS_TEMPLATE, JsonEditor } from "@/components/ui/json-editor";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";

import type { McpClaudeDesktopImportResult, McpCustomServerEntry } from "@/lib/control-plane";

/*  Types                                                              */

type Mode = "form" | "json";

type EnvFieldDraft = {
  _id: number;
  key: string;
  label: string;
  required: boolean;
};

type HeaderDraft = {
  _id: number;
  key: string;
};

type ScopeChoice = "system" | "agent";

export type McpCustomServerSubmitInput = {
  scope: ScopeChoice;
  payload: Record<string, unknown>;
};

export type McpCustomServerImportInput = {
  scope: ScopeChoice;
  raw: { mcpServers?: Record<string, unknown> } | Record<string, unknown>;
};

export type McpCustomServerModalProps = {
  open: boolean;
  onClose: () => void;
  onSubmitForm: (input: McpCustomServerSubmitInput) => Promise<McpCustomServerEntry>;
  onSubmitImport: (input: McpCustomServerImportInput) => Promise<McpClaudeDesktopImportResult>;
  defaultMode?: Mode;
  defaultScope?: ScopeChoice;
  hideScopePicker?: boolean;
  agentLabel?: string;
};

/*  State helpers                                                      */

let _envFieldId = 0;
function nextId(): number {
  _envFieldId += 1;
  return _envFieldId;
}

function emptyEnv(): EnvFieldDraft {
  return { _id: nextId(), key: "", label: "", required: true };
}

function emptyHeader(): HeaderDraft {
  return { _id: nextId(), key: "Authorization" };
}

const SAFE_COMMANDS = ["npx", "uvx", "node", "python", "python3", "deno", "bun", "docker"];

const SAMPLE_JSON = EMPTY_MCP_SERVERS_TEMPLATE;

/*  Component                                                          */

export function McpCustomServerModal({
  open,
  onClose,
  onSubmitForm,
  onSubmitImport,
  defaultMode = "form",
  defaultScope = "system",
  hideScopePicker = false,
  agentLabel,
}: McpCustomServerModalProps) {
  const { t } = useAppI18n();

  const [mode, setMode] = useState<Mode>(defaultMode);
  const [scope, setScope] = useState<ScopeChoice>(defaultScope);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<McpClaudeDesktopImportResult | null>(null);

  // Form state
  const [serverKey, setServerKey] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [transport, setTransport] = useState<"stdio" | "http_sse">("stdio");
  const [command, setCommand] = useState("npx");
  const [args, setArgs] = useState("");
  const [url, setUrl] = useState("");
  const [envFields, setEnvFields] = useState<EnvFieldDraft[]>([]);
  const [headers, setHeaders] = useState<HeaderDraft[]>([]);
  const [authStrategy, setAuthStrategy] = useState<"no_auth" | "api_key" | "oauth">("no_auth");
  const [oauthMetadataUrl, setOauthMetadataUrl] = useState("");
  const [oauthScopes, setOauthScopes] = useState("");

  // JSON state
  const [jsonRaw, setJsonRaw] = useState(SAMPLE_JSON);
  const jsonParsed = useMemo(() => {
    try {
      return JSON.parse(jsonRaw) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [jsonRaw]);
  const detectedServers = useMemo(() => {
    if (!jsonParsed) return [] as string[];
    const servers = (jsonParsed as { mcpServers?: Record<string, unknown> }).mcpServers;
    if (!servers || typeof servers !== "object") return [];
    return Object.keys(servers);
  }, [jsonParsed]);

  // Sync mode with defaultMode whenever the modal opens.
  useEffect(() => {
    if (open) setMode(defaultMode);
  }, [open, defaultMode]);

  // Canonical glass-blur dialog plumbing — matches every other Koda modal:
  // mount/unmount delayed by exit animation, body scroll locked, ESC closes.
  const presence = useAnimatedPresence(open, null, { duration: 200 });
  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, onClose);

  const reset = useCallback(() => {
    setServerKey("");
    setDisplayName("");
    setDescription("");
    setTransport("stdio");
    setCommand("npx");
    setArgs("");
    setUrl("");
    setEnvFields([]);
    setHeaders([]);
    setAuthStrategy("no_auth");
    setOauthMetadataUrl("");
    setOauthScopes("");
    setJsonRaw(SAMPLE_JSON);
    setError(null);
    setImportResult(null);
  }, []);

  const handleSubmitForm = useCallback(async () => {
    setError(null);
    if (!serverKey.trim() || !displayName.trim()) {
      setError(t("generated.controlPlane.identificador_e_nome_de_exibicao_sao_obrigat_1c539111"));
      return;
    }
    if (transport === "stdio" && !command.trim()) {
      setError(t("generated.controlPlane.comando_e_obrigatorio_para_transport_stdio_c37c6033"));
      return;
    }
    if (transport === "http_sse" && !url.trim()) {
      setError(t("generated.controlPlane.url_e_obrigatoria_para_transport_http_sse_d3290c4e"));
      return;
    }
    setSubmitting(true);
    try {
      const argsList = args
        .split(/\s+/)
        .map((piece) => piece.trim())
        .filter((piece) => piece.length > 0);
      const oauthConfig =
        authStrategy === "oauth"
          ? {
              oauth_metadata_url: oauthMetadataUrl.trim() || undefined,
              scopes: oauthScopes
                .split(/[\s,]+/)
                .map((scope) => scope.trim())
                .filter((scope) => scope.length > 0),
            }
          : {};

      const payload: Record<string, unknown> = {
        server_key: serverKey.trim(),
        display_name: displayName.trim(),
        description: description.trim(),
        transport_type: transport,
        command: transport === "stdio" ? [command.trim(), ...argsList] : [],
        url: transport === "http_sse" ? url.trim() : null,
        env_schema: envFields
          .filter((f) => f.key.trim())
          .map(({ key, label, required }) => ({
            key: key.trim().toUpperCase(),
            label: label.trim() || key.trim(),
            required,
            input_type: "password",
          })),
        headers_schema: headers
          .filter((h) => h.key.trim())
          .map((h) => ({ key: h.key.trim() })),
        auth_strategy: authStrategy,
        oauth_config: oauthConfig,
      };
      await onSubmitForm({ scope, payload });
      reset();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("generated.controlPlane.falha_ao_registrar_servidor_c73de07f"));
    } finally {
      setSubmitting(false);
    }
  }, [
    args,
    authStrategy,
    command,
    description,
    displayName,
    envFields,
    headers,
    oauthMetadataUrl,
    oauthScopes,
    onClose,
    onSubmitForm,
    reset,
    scope,
    serverKey,
    t,
    transport,
    url,
  ]);

  const handleSubmitJson = useCallback(async () => {
    setError(null);
    setImportResult(null);
    if (!jsonParsed) {
      setError(t("generated.controlPlane.json_invalido_verifique_a_sintaxe_63ba115e"));
      return;
    }
    if (detectedServers.length === 0) {
      setError(t("generated.controlPlane.nenhum_servidor_encontrado_em_mcpservers_e38cb2b8"));
      return;
    }
    setSubmitting(true);
    try {
      const result = await onSubmitImport({ scope, raw: jsonParsed });
      setImportResult(result);
      if (result.errors.length === 0) {
        setTimeout(() => {
          reset();
          onClose();
        }, 1200);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("generated.controlPlane.falha_ao_importar_json_b1f012b0"));
    } finally {
      setSubmitting(false);
    }
  }, [detectedServers.length, jsonParsed, onClose, onSubmitImport, reset, scope, t]);

  if (!presence.shouldRender || typeof document === "undefined") return null;

  const isStdio = transport === "stdio";
  const submitDisabled =
    submitting || (mode === "json" && (!jsonParsed || detectedServers.length === 0));
  const submitLabel = submitting
    ? t("generated.controlPlane.salvando_7eeded02")
    : mode === "form"
      ? t("generated.controlPlane.adicionar_07558363")
      : detectedServers.length > 0
        ? `${t("generated.controlPlane.importar_31652d9a")} (${detectedServers.length})`
        : t("generated.controlPlane.importar_31652d9a");

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        data-visible={presence.isVisible}
        data-state={presence.dataState}
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel app-modal-anim relative w-full max-w-2xl max-h-[calc(100vh-4rem)] flex flex-col"
          data-visible={presence.isVisible}
          data-state={presence.dataState}
          role="dialog"
          aria-modal="true"
          aria-labelledby="mcp-custom-modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <button type="button" onClick={onClose} className="app-surface-close" aria-label={t("generated.controlPlane.fechar_modal_1b5b2901")}>
            <X className="h-4 w-4" />
          </button>

          {/* Compact header — title + tabs + scope all on one band */}
          <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-6 py-3 pr-14">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--panel-soft)]">
              {renderIntegrationLogo("mcp", "h-5 w-5") || <Plus size={16} />}
            </div>
            <h3 id="mcp-custom-modal-title" className="text-base font-semibold text-[var(--text-primary)]">
              {t("generated.controlPlane.adicionar_servidor_mcp_ea88d544")}
            </h3>
            <div className="ml-auto flex items-center gap-2">
              <SoftTabs
                value={mode}
                onChange={(id) => setMode(id as Mode)}
                ariaLabel={t("generated.controlPlane.modo_49a7c7ce")}
                items={[
                  { id: "form", label: t("generated.controlPlane.formulario_a8928c88") },
                  { id: "json", label: "JSON" },
                ]}
              />
              {!hideScopePicker ? (
                <Select value={scope} onValueChange={(v) => setScope(v as ScopeChoice)}>
                  <SelectTrigger sizeVariant="sm" className="w-auto whitespace-nowrap">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="system">{t("generated.controlPlane.todos_os_agentes_ab31c2fa")}</SelectItem>
                    <SelectItem value="agent">
                      {agentLabel ? t("generated.controlPlane.apenas_label_5e81bc92", { label: agentLabel }) : t("generated.controlPlane.apenas_este_agente_99214fa9")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              ) : null}
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
            {mode === "form" ? (
              <FormBody
                serverKey={serverKey}
                setServerKey={setServerKey}
                displayName={displayName}
                setDisplayName={setDisplayName}
                description={description}
                setDescription={setDescription}
                transport={transport}
                setTransport={setTransport}
                command={command}
                setCommand={setCommand}
                args={args}
                setArgs={setArgs}
                url={url}
                setUrl={setUrl}
                envFields={envFields}
                setEnvFields={setEnvFields}
                headers={headers}
                setHeaders={setHeaders}
                authStrategy={authStrategy}
                setAuthStrategy={setAuthStrategy}
                oauthMetadataUrl={oauthMetadataUrl}
                setOauthMetadataUrl={setOauthMetadataUrl}
                oauthScopes={oauthScopes}
                setOauthScopes={setOauthScopes}
                isStdio={isStdio}
              />
            ) : (
              <JsonBody
                value={jsonRaw}
                onChange={setJsonRaw}
                importResult={importResult}
              />
            )}
            {error ? (
              <p className="mt-3 text-xs font-medium text-[var(--tone-danger-dot)]">{error}</p>
            ) : null}
          </div>

          {/* Footer — buttons only */}
          <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-6 py-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)]"
            >
              {t("generated.controlPlane.cancelar_091200fb")}
            </button>
            <button
              type="button"
              onClick={mode === "form" ? handleSubmitForm : handleSubmitJson}
              disabled={submitDisabled}
              className="inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 text-xs font-semibold text-[var(--interactive-active-text)] transition-all disabled:opacity-50"
              style={{
                background:
                  "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                border: "1px solid var(--interactive-active-border)",
              }}
            >
              {submitLabel}
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}

/*  Form body                                                          */

type FormBodyProps = {
  serverKey: string;
  setServerKey: (v: string) => void;
  displayName: string;
  setDisplayName: (v: string) => void;
  description: string;
  setDescription: (v: string) => void;
  transport: "stdio" | "http_sse";
  setTransport: (v: "stdio" | "http_sse") => void;
  command: string;
  setCommand: (v: string) => void;
  args: string;
  setArgs: (v: string) => void;
  url: string;
  setUrl: (v: string) => void;
  envFields: EnvFieldDraft[];
  setEnvFields: (v: EnvFieldDraft[]) => void;
  headers: HeaderDraft[];
  setHeaders: (v: HeaderDraft[]) => void;
  authStrategy: "no_auth" | "api_key" | "oauth";
  setAuthStrategy: (v: "no_auth" | "api_key" | "oauth") => void;
  oauthMetadataUrl: string;
  setOauthMetadataUrl: (v: string) => void;
  oauthScopes: string;
  setOauthScopes: (v: string) => void;
  isStdio: boolean;
};

function FormBody(props: FormBodyProps) {
  const { t } = useAppI18n();

  return (
    <div className="flex flex-col gap-3">
      {/* Row 1: slug + display name */}
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("generated.controlPlane.identificador_91c92cf4")}>
          <Input
            sizeVariant="sm"
            value={props.serverKey}
            onChange={(e) => props.setServerKey(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-"))}
            placeholder={translate("generated.controlPlane.meu_servidor_429b287a")}
          />
        </Field>
        <Field label={t("generated.controlPlane.nome_fb4c2d32")}>
          <Input
            sizeVariant="sm"
            value={props.displayName}
            onChange={(e) => props.setDisplayName(e.target.value)}
            placeholder={t("generated.controlPlane.meu_servidor_mcp_701fba25")}
          />
        </Field>
      </div>

      {/* Row 2: description */}
      <Field label={t("generated.controlPlane.descricao_ff40fdea")}>
        <Input
          sizeVariant="sm"
          value={props.description}
          onChange={(e) => props.setDescription(e.target.value)}
          placeholder={t("generated.controlPlane.opcional_f6c7765c")}
        />
      </Field>

      {/* Row 3: transport */}
      <Field label={t("generated.controlPlane.transport_90314978")}>
        <Select value={props.transport} onValueChange={(v) => props.setTransport(v as "stdio" | "http_sse")}>
          <SelectTrigger sizeVariant="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="stdio">{t("generated.controlPlane.stdio_0fdf75ed")}</SelectItem>
            <SelectItem value="http_sse">{t("generated.controlPlane.http_sse_66f69e6a")}</SelectItem>
          </SelectContent>
        </Select>
      </Field>

      {/* Row 4: command + args (stdio) OR URL (http_sse) */}
      {props.isStdio ? (
        <div className="grid grid-cols-[8rem_1fr] gap-3">
          <Field label={t("generated.controlPlane.comando_b21ea3ed")}>
            <Select value={props.command} onValueChange={props.setCommand}>
              <SelectTrigger sizeVariant="sm" title={SAFE_COMMANDS.join(", ")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SAFE_COMMANDS.map((cmd) => (
                  <SelectItem key={cmd} value={cmd}>
                    {cmd}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label={t("generated.controlPlane.argumentos_8bbda937")}>
            <Input
              sizeVariant="sm"
              className="font-mono"
              value={props.args}
              onChange={(e) => props.setArgs(e.target.value)}
              placeholder={translate("generated.controlPlane.y_minha_empresa_mcp_29187fa4")}
            />
          </Field>
        </div>
      ) : (
        <Field label="URL">
          <Input
            sizeVariant="sm"
            value={props.url}
            onChange={(e) => props.setUrl(e.target.value)}
            placeholder="https://mcp.exemplo.com/sse"
          />
        </Field>
      )}

      {/* Env vars */}
      <EnvSchemaBuilder fields={props.envFields} setFields={props.setEnvFields} />

      {/* HTTP headers */}
      {!props.isStdio ? <HeadersBuilder headers={props.headers} setHeaders={props.setHeaders} /> : null}

      {/* Row: auth */}
      <Field label={t("generated.controlPlane.autenticacao_023abe86")}>
        <Select value={props.authStrategy} onValueChange={(v) => props.setAuthStrategy(v as "no_auth" | "api_key" | "oauth")}>
          <SelectTrigger sizeVariant="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="no_auth">{t("generated.controlPlane.sem_autenticacao_e1817db6")}</SelectItem>
            <SelectItem value="api_key">{translate("generated.controlPlane.api_key_372f7809")}</SelectItem>
            <SelectItem value="oauth">{translate("generated.controlPlane.oauth_2_1_c7c2ea30")}</SelectItem>
          </SelectContent>
        </Select>
      </Field>

      {/* OAuth fields */}
      {props.authStrategy === "oauth" ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[2fr_1fr]">
          <Field label={t("generated.controlPlane.metadata_url_94f81263")}>
            <Input
              sizeVariant="sm"
              value={props.oauthMetadataUrl}
              onChange={(e) => props.setOauthMetadataUrl(e.target.value)}
              placeholder="https://.../.well-known/oauth-authorization-server"
            />
          </Field>
          <Field label={translate("generated.controlPlane.scopes_dd3d996a")}>
            <Input
              sizeVariant="sm"
              value={props.oauthScopes}
              onChange={(e) => props.setOauthScopes(e.target.value)}
              placeholder={translate("generated.controlPlane.read_write_ff1164d8")}
            />
          </Field>
        </div>
      ) : null}
    </div>
  );
}

/*  Field — single label + control row, no description noise           */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
        {label}
      </span>
      {children}
    </label>
  );
}

/*  Sub-builders                                                       */

function EnvSchemaBuilder({
  fields,
  setFields,
}: {
  fields: EnvFieldDraft[];
  setFields: (fields: EnvFieldDraft[]) => void;
}) {
  const { t } = useAppI18n();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
          {t("generated.controlPlane.variaveis_de_ambiente_fc3cabe2")}
        </span>
        <button
          type="button"
          onClick={() => setFields([...fields, emptyEnv()])}
          aria-label={t("generated.controlPlane.nova_variavel_17e0a7c8")}
          title={t("generated.controlPlane.nova_variavel_17e0a7c8")}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          <Plus size={11} />
        </button>
      </div>
      {fields.length === 0 ? null : (
        <div className="flex flex-col gap-1.5">
          {fields.map((field) => (
            <div key={field._id} className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2">
              <Input
                sizeVariant="sm"
                value={field.key}
                onChange={(e) =>
                  setFields(
                    fields.map((f) =>
                      f._id === field._id ? { ...f, key: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") } : f,
                    ),
                  )
                }
                placeholder="MY_TOKEN"
              />
              <Input
                sizeVariant="sm"
                value={field.label}
                onChange={(e) =>
                  setFields(fields.map((f) => (f._id === field._id ? { ...f, label: e.target.value } : f)))
                }
                placeholder={t("generated.controlPlane.rotulo_18b7d611")}
              />
              <label className="flex items-center gap-1 whitespace-nowrap text-[10px] text-[var(--text-quaternary)]">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={() =>
                    setFields(fields.map((f) => (f._id === field._id ? { ...f, required: !f.required } : f)))
                  }
                />
                {t("generated.controlPlane.obrigatorio_ea9fd1bf")}
              </label>
              <button
                type="button"
                onClick={() => setFields(fields.filter((f) => f._id !== field._id))}
                className="rounded p-1 text-[var(--text-tertiary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                aria-label={t("generated.controlPlane.remover_5465770e")}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HeadersBuilder({
  headers,
  setHeaders,
}: {
  headers: HeaderDraft[];
  setHeaders: (h: HeaderDraft[]) => void;
}) {
  const { t } = useAppI18n();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
          {t("generated.controlPlane.headers_http_71f40bc9")}
        </span>
        <button
          type="button"
          onClick={() => setHeaders([...headers, emptyHeader()])}
          aria-label={t("generated.controlPlane.novo_header_959c3951")}
          title={t("generated.controlPlane.novo_header_959c3951")}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          <Plus size={11} />
        </button>
      </div>
      {headers.length === 0 ? null : (
        <div className="flex flex-col gap-1.5">
          {headers.map((h) => (
            <div key={h._id} className="grid grid-cols-[1fr_auto] items-center gap-2">
              <Input
                sizeVariant="sm"
                value={h.key}
                onChange={(e) =>
                  setHeaders(headers.map((it) => (it._id === h._id ? { ...it, key: e.target.value } : it)))
                }
                placeholder={translate("generated.controlPlane.x_api_key_0da7d9b1")}
              />
              <button
                type="button"
                onClick={() => setHeaders(headers.filter((it) => it._id !== h._id))}
                className="rounded p-1 text-[var(--text-tertiary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                aria-label={t("generated.controlPlane.remover_5465770e")}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/*  JSON body                                                          */

function JsonBody({
  value,
  onChange,
  importResult,
}: {
  value: string;
  onChange: (v: string) => void;
  importResult: McpClaudeDesktopImportResult | null;
}) {
  const { t } = useAppI18n();
  return (
    <div className="flex flex-col gap-2">
      <JsonEditor value={value} onChange={onChange} rows={14} ariaLabel="JSON" />
      {importResult ? (
        <div className="flex flex-col gap-1 text-xs">
          {importResult.created.length > 0 ? (
            <p className="text-[var(--tone-success-text)]">
              {t("generated.controlPlane.criados_names_db1d0de6", { names: importResult.created.join(", ") })}
            </p>
          ) : null}
          {importResult.updated.length > 0 ? (
            <p className="text-[var(--text-secondary)]">
              {t("generated.controlPlane.atualizados_names_45415321", { names: importResult.updated.join(", ") })}
            </p>
          ) : null}
          {importResult.errors.length > 0 ? (
            <ul className="list-disc pl-5 text-[var(--tone-danger-dot)]">
              {importResult.errors.map((err, idx) => (
                <li key={`${err.name}-${idx}`}>
                  <strong>{err.name}</strong>: {err.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
