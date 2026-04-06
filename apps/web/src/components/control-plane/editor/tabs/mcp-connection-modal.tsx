"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, Lock, Loader2, Puzzle, X, XCircle, Zap } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SecretInput } from "@/components/ui/secret-controls";
import { requestJson } from "@/lib/http-client";
import type { McpAgentConnection, McpEnvSchemaField, McpServerCatalogEntry } from "@/lib/control-plane";

type McpConnectionModalProps = {
  server: McpServerCatalogEntry;
  agentId: string;
  existingConnection?: McpAgentConnection | null;
  onClose: () => void;
  onSaved: () => void;
};

export function McpConnectionModal({
  server,
  agentId,
  existingConnection,
  onClose,
  onSaved,
}: McpConnectionModalProps) {
  const { tl } = useAppI18n();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const envSchema = useMemo<McpEnvSchemaField[]>(() => {
    try {
      const parsed = JSON.parse(server.env_schema_json || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [server.env_schema_json]);

  const existingSecretKeys = useMemo(
    () => new Set(Object.keys(existingConnection?.env_values ?? {})),
    [existingConnection],
  );

  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [transportOverride, setTransportOverride] = useState(
    existingConnection?.transport_override ?? "",
  );
  const [urlOverride, setUrlOverride] = useState(existingConnection?.url_override ?? "");

  // Escape to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    const initial: Record<string, string> = {};
    for (const field of envSchema) {
      initial[field.key] = "";
    }
    setEnvValues(initial);
    setTransportOverride(existingConnection?.transport_override ?? "");
    setUrlOverride(existingConnection?.url_override ?? "");
    setError(null);
    setTestResult(null);
  }, [envSchema, existingConnection, server.server_key]);

  // Auto-focus first input
  useEffect(() => {
    const timer = setTimeout(() => {
      const el = document.querySelector<HTMLInputElement>(
        "[data-mcp-connection-modal] input",
      );
      el?.focus();
    }, 80);
    return () => clearTimeout(timer);
  }, []);

  const updateEnvValue = useCallback((key: string, value: string) => {
    setEnvValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  const resolvedEnvValues = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(envValues).filter(([, value]) => value.trim().length > 0),
      ) as Record<string, string>,
    [envValues],
  );

  const missingRequiredFields = useMemo(
    () =>
      envSchema.filter(
        (field) =>
          field.required &&
          !resolvedEnvValues[field.key] &&
          !existingSecretKeys.has(field.key),
      ),
    [envSchema, existingSecretKeys, resolvedEnvValues],
  );

  const validateRequiredFields = useCallback(() => {
    if (missingRequiredFields.length === 0) return true;
    const labels = missingRequiredFields
      .map((field) => field.label || field.key)
      .join(", ");
    setError(
      tl("Preencha os campos obrigatorios: {{fields}}.", {
        fields: labels,
      }),
    );
    return false;
  }, [missingRequiredFields, tl]);

  const handleSave = useCallback(async () => {
    if (!validateRequiredFields()) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const connectionKey = `mcp:${server.server_key}`;
      const payload: Record<string, unknown> = {
        enabled: true,
        env_values: resolvedEnvValues,
        ...(transportOverride ? { transport_override: transportOverride } : {}),
        ...(urlOverride ? { url_override: urlOverride } : {}),
      };
      await requestJson(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}`,
        { method: "PUT", body: JSON.stringify(payload) },
      );
      onSaved();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : tl("Erro ao salvar conexao"),
      );
    } finally {
      setSaving(false);
    }
  }, [
    agentId,
    server.server_key,
    resolvedEnvValues,
    transportOverride,
    urlOverride,
    onSaved,
    tl,
    validateRequiredFields,
  ]);

  const handleTest = useCallback(async () => {
    if (!validateRequiredFields()) {
      return;
    }
    setTesting(true);
    setTestResult(null);
    setError(null);
    try {
      const connectionKey = `mcp:${server.server_key}`;
      // Save credentials first (backend reads from DB)
      const payload: Record<string, unknown> = {
        enabled: true,
        env_values: resolvedEnvValues,
        ...(transportOverride ? { transport_override: transportOverride } : {}),
        ...(urlOverride ? { url_override: urlOverride } : {}),
      };
      await requestJson(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}`,
        { method: "PUT", body: JSON.stringify(payload) },
      );
      // Now test the connection
      const result = await requestJson<{
        success?: boolean;
        healthy?: boolean;
        tool_count?: number;
        error?: string;
      }>(
        `/api/control-plane/agents/${agentId}/connections/${encodeURIComponent(connectionKey)}/verify`,
        { method: "POST" },
      );
      if (result.success) {
        setTestResult({
          success: true,
          message: tl("Conexao valida") +
            (result.tool_count ? ` (${result.tool_count} tools)` : ""),
        });
      } else {
        setTestResult({
          success: false,
          message: result.error || tl("Falha na conexao"),
        });
      }
    } catch (err) {
      // Handle 501 Not Implemented gracefully
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("501") || msg.includes("Not Implemented")) {
        setTestResult({
          success: false,
          message: tl("Teste nao disponivel"),
        });
      } else {
        setTestResult({
          success: false,
          message: msg || tl("Erro ao testar conexao"),
        });
      }
    } finally {
      setTesting(false);
    }
  }, [
    agentId,
    server.server_key,
    resolvedEnvValues,
    transportOverride,
    urlOverride,
    tl,
    validateRequiredFields,
  ]);

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
          aria-labelledby="mcp-connection-modal-title"
          data-mcp-connection-modal
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          {/* Header */}
          <div className="border-b border-[var(--border-subtle)] px-6 py-5 pr-14">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[var(--tone-info-border)] bg-[var(--tone-info-bg)]">
                <Puzzle className="h-6 w-6 text-[var(--tone-info-dot)]" />
              </div>
              <div>
                <h3
                  id="mcp-connection-modal-title"
                  className="text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]"
                >
                  {existingConnection
                    ? tl("Editar conexao")
                    : tl("Conectar")}{" "}
                  {server.display_name}
                </h3>
                <p className="mt-0.5 text-sm text-[var(--text-quaternary)]">
                  {server.description || tl("Servidor MCP")}
                </p>
              </div>
            </div>
          </div>

          {/* Credential fields */}
          <div className="flex-1 overflow-y-auto space-y-4 px-6 py-5">
            {envSchema.length === 0 && (
              <p className="text-sm text-[var(--text-tertiary)]">
                {tl("Nenhuma credencial necessaria para este servidor.")}
              </p>
            )}
            {envSchema.map((field) => (
              <label key={field.key} className="flex flex-col gap-2 px-1 py-1">
                <div className="flex min-h-[2rem] flex-col">
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                      {field.label || field.key}
                    </div>
                    <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-quaternary)]">
                      {field.required ? tl("Obrigatorio") : tl("Opcional")}
                    </p>
                    {existingSecretKeys.has(field.key) && (
                      <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-quaternary)]">
                        {tl("Ja configurado; deixe em branco para manter o valor atual.")}
                      </p>
                    )}
                  </div>
                </div>
                {field.input_type === "password" ? (
                  <SecretInput
                    value={envValues[field.key] ?? ""}
                    onChange={(e) => updateEnvValue(field.key, e.target.value)}
                    placeholder={
                      existingSecretKeys.has(field.key)
                        ? tl("Mantido da conexao atual")
                        : tl("Digite o valor")
                    }
                  />
                ) : (
                  <input
                    className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
                    type="text"
                    value={envValues[field.key] ?? ""}
                    onChange={(e) => updateEnvValue(field.key, e.target.value)}
                    placeholder={
                      existingSecretKeys.has(field.key)
                        ? tl("Mantido da conexao atual")
                        : tl("Preencha o valor")
                    }
                  />
                )}
              </label>
            ))}

            {error && (
              <div className="rounded-xl border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-4 py-3 text-xs text-[var(--tone-danger-text)]">
                {error}
              </div>
            )}

            {/* Advanced configuration */}
            <details className="mt-4 border-t border-[var(--border-subtle)] pt-3">
              <summary className="cursor-pointer text-xs font-medium text-[var(--text-quaternary)] hover:text-[var(--text-tertiary)]">
                {tl("Configuracao avancada")}
              </summary>
              <div className="mt-3 flex flex-col gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-quaternary)]">
                    {tl("Tipo de transporte")}
                  </span>
                  <select
                    value={transportOverride}
                    onChange={(e) => setTransportOverride(e.target.value)}
                    className="field-shell rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="">{tl("Padrao do servidor")}</option>
                    <option value="stdio">stdio</option>
                    <option value="http_sse">HTTP SSE</option>
                  </select>
                </label>
                {/* URL override (for http_sse) */}
                {transportOverride === "http_sse" && (
                  <label className="flex flex-col gap-1">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-quaternary)]">
                      {tl("URL do servidor")}
                    </span>
                    <input
                      type="text"
                      value={urlOverride}
                      onChange={(e) => setUrlOverride(e.target.value)}
                      placeholder="https://..."
                      className="field-shell rounded-lg px-3 py-2 text-sm"
                    />
                  </label>
                )}
              </div>
            </details>
          </div>

          {/* Test result (inline) */}
          {testResult && (
            <div
              className={`mx-6 mb-4 flex items-center gap-2 rounded-xl border px-4 py-2.5 text-xs ${
                testResult.success
                  ? "border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]"
                  : "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]"
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 size={13} className="shrink-0" />
              ) : (
                <XCircle size={13} className="shrink-0" />
              )}
              <span>{testResult.message}</span>
            </div>
          )}

          {/* Footer */}
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
              <button
                type="button"
                onClick={handleTest}
                disabled={testing || saving}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-4 py-2 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-50"
              >
                {testing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Zap size={13} />
                )}
                {testing ? tl("Testando...") : tl("Testar conexao")}
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || testing}
                className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-[var(--interactive-active-text)] transition-all disabled:opacity-50"
                style={{
                  background:
                    "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                  border: "1px solid var(--interactive-active-border)",
                }}
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                {saving ? tl("Salvando") : tl("Salvar conexao")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
