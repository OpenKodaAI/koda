"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { X, Plus, Trash2 } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { McpServerCatalogEntry, McpEnvSchemaField } from "@/lib/control-plane";
import {
  MCP_CATEGORY_LABELS,
  isReservedMcpServerKey,
  type McpCategory,
} from "./mcp-catalog-data";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type EnvFieldDraft = McpEnvSchemaField & { _id: number };

type EditorFormState = {
  server_key: string;
  display_name: string;
  description: string;
  transport_type: "stdio" | "http_sse";
  command: string;
  url: string;
  documentation_url: string;
  logo_key: string;
  category: McpCategory;
  env_fields: EnvFieldDraft[];
};

let _envFieldId = 0;

function nextEnvFieldId() {
  return ++_envFieldId;
}

function emptyEnvField(): EnvFieldDraft {
  return {
    _id: nextEnvFieldId(),
    key: "",
    label: "",
    required: true,
    input_type: "password",
  };
}

function formStateFromServer(server: McpServerCatalogEntry): EditorFormState {
  let envFields: EnvFieldDraft[] = [];
  try {
    const parsed = JSON.parse(server.env_schema_json || "[]") as McpEnvSchemaField[];
    envFields = parsed.map((f) => ({ ...f, _id: nextEnvFieldId() }));
  } catch {
    /* empty */
  }

  let command = "";
  try {
    const parsed = JSON.parse(server.command_json || "[]") as string[];
    command = parsed.join(" ");
  } catch {
    command = server.command_json ?? "";
  }

  return {
    server_key: server.server_key,
    display_name: server.display_name,
    description: server.description,
    transport_type: server.transport_type,
    command,
    url: server.url ?? "",
    documentation_url: server.documentation_url ?? "",
    logo_key: server.logo_key ?? "",
    category: (server.category as McpCategory) || "general",
    env_fields: envFields,
  };
}

function emptyFormState(): EditorFormState {
  return {
    server_key: "",
    display_name: "",
    description: "",
    transport_type: "stdio",
    command: "",
    url: "",
    documentation_url: "",
    logo_key: "",
    category: "general",
    env_fields: [],
  };
}

/* ------------------------------------------------------------------ */
/*  Env Schema Builder                                                 */
/* ------------------------------------------------------------------ */

function EnvSchemaBuilder({
  fields,
  onChange,
}: {
  fields: EnvFieldDraft[];
  onChange: (fields: EnvFieldDraft[]) => void;
}) {
  const { tl } = useAppI18n();

  const updateField = (id: number, patch: Partial<EnvFieldDraft>) => {
    onChange(fields.map((f) => (f._id === id ? { ...f, ...patch } : f)));
  };

  const removeField = (id: number) => {
    onChange(fields.filter((f) => f._id !== id));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
          {tl("Variaveis de ambiente")}
        </span>
        <button
          type="button"
          onClick={() => onChange([...fields, emptyEnvField()])}
          className="button-shell button-shell--secondary button-shell--sm gap-1 px-3"
        >
          <Plus size={12} />
          <span>{tl("Adicionar")}</span>
        </button>
      </div>

      {fields.length === 0 ? (
        <p className="text-xs text-[var(--text-quaternary)]">
          {tl("Nenhuma variavel de ambiente configurada.")}
        </p>
      ) : (
        <div className="space-y-2">
          {fields.map((field) => (
            <div
              key={field._id}
              className="flex items-start gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] p-3"
            >
              <div className="grid flex-1 grid-cols-2 gap-2">
                <input
                  className="field-shell px-3 py-1.5 text-xs text-[var(--text-primary)]"
                  value={field.key}
                  onChange={(e) =>
                    updateField(field._id, {
                      key: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""),
                    })
                  }
                  placeholder="CHAVE"
                />
                <input
                  className="field-shell px-3 py-1.5 text-xs text-[var(--text-primary)]"
                  value={field.label}
                  onChange={(e) => updateField(field._id, { label: e.target.value })}
                  placeholder={tl("Rotulo")}
                />
              </div>
              <label className="flex items-center gap-1 whitespace-nowrap pt-1.5 text-[10px] text-[var(--text-quaternary)]">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={() => updateField(field._id, { required: !field.required })}
                  className="accent-[var(--interactive-active-border)]"
                />
                {tl("Obrigatorio")}
              </label>
              <button
                type="button"
                onClick={() => removeField(field._id)}
                className="shrink-0 rounded border border-transparent p-1 text-[var(--tone-danger-text)] transition-colors hover:border-[var(--tone-danger-border)] hover:bg-[var(--tone-danger-bg)]"
                aria-label={tl("Remover campo")}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Editor Modal                                                       */
/* ------------------------------------------------------------------ */

export function McpServerEditorModal({
  server,
  mode,
  lockServerKey = false,
  onClose,
  onSave,
  saving,
}: {
  server: McpServerCatalogEntry | null;
  mode?: "create" | "edit";
  lockServerKey?: boolean;
  onClose: () => void;
  onSave: (serverKey: string, payload: Partial<McpServerCatalogEntry>) => Promise<void>;
  saving?: boolean;
}) {
  const { tl } = useAppI18n();
  const isEditing = mode ? mode === "edit" : server !== null;
  const [form, setForm] = useState<EditorFormState>(
    server ? formStateFromServer(server) : emptyFormState(),
  );
  const normalizedServerKey = form.server_key.trim().toLowerCase();
  const isReservedServerKey =
    normalizedServerKey.length > 0 && isReservedMcpServerKey(normalizedServerKey);

  const patch = useCallback(
    (updates: Partial<EditorFormState>) => setForm((prev) => ({ ...prev, ...updates })),
    [],
  );

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

  const handleSubmit = async () => {
    if (isReservedServerKey) {
      return;
    }

    const commandJson =
      form.transport_type === "stdio"
        ? JSON.stringify(form.command.split(/\s+/).filter(Boolean))
        : "[]";

    const envSchemaJson = JSON.stringify(
      form.env_fields
        .filter((f) => f.key.trim())
        .map(({ key, label, required, input_type }) => ({
          key,
          label: label || key,
          required,
          input_type,
        })),
    );

    const key = isEditing
      ? form.server_key
      : form.server_key
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9_-]/g, "-");

    await onSave(key, {
      display_name: form.display_name,
      description: form.description,
      transport_type: form.transport_type,
      command_json: commandJson,
      url: form.transport_type === "http_sse" ? form.url : null,
      documentation_url: form.documentation_url || null,
      logo_key: form.logo_key.trim() || null,
      category: form.category,
      env_schema_json: envSchemaJson,
      enabled: server?.enabled ?? true,
    });
  };

  if (typeof document === "undefined") return null;

  const canSave =
    Boolean(form.server_key.trim()) &&
    Boolean(form.display_name.trim()) &&
    Boolean(form.transport_type === "stdio" ? form.command.trim() : form.url.trim()) &&
    !isReservedServerKey;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] overflow-y-auto px-4 py-6 sm:px-6">
        <div
          className="app-modal-panel relative flex max-h-[min(86vh,58rem)] w-full max-w-2xl flex-col overflow-hidden"
          role="dialog"
          aria-modal="true"
          aria-labelledby="mcp-editor-modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar modal")}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-5 py-5 pr-14 sm:px-6 sm:pr-16">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {isEditing ? tl("Servidor MCP") : tl("Novo servidor MCP")}
              </p>
              <h3
                id="mcp-editor-modal-title"
                className="text-[1.15rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)] sm:text-[1.2rem]"
              >
                {isEditing
                  ? tl("Editar servidor MCP")
                  : tl("Adicionar servidor MCP")}
              </h3>
              <p className="max-w-[38rem] text-sm leading-6 text-[var(--text-quaternary)]">
                {tl("Configure a conexao global com um servidor MCP externo.")}
              </p>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6 sm:py-6">
            <div className="space-y-4">
              <FieldShell
                label="Identificador (slug)"
                description={
                  isReservedServerKey
                    ? tl("Este identificador e reservado e nao pode ser usado.")
                    : tl("Chave unica do servidor")
                }
              >
                <input
                  className="field-shell text-[var(--text-primary)]"
                  value={form.server_key}
                  onChange={(e) => patch({ server_key: e.target.value })}
                  placeholder="meu-servidor"
                  disabled={isEditing || lockServerKey}
                  aria-invalid={isReservedServerKey}
                />
              </FieldShell>

              <FieldShell label="Nome de exibicao">
                <input
                  className="field-shell text-[var(--text-primary)]"
                  value={form.display_name}
                  onChange={(e) => patch({ display_name: e.target.value })}
                  placeholder="Meu Servidor MCP"
                />
              </FieldShell>

              <FieldShell label="Descricao">
                <textarea
                  className="field-shell min-h-[60px] resize-y text-[var(--text-primary)]"
                  value={form.description}
                  onChange={(e) => patch({ description: e.target.value })}
                  placeholder={tl("Breve descricao do que esse servidor oferece")}
                />
              </FieldShell>

              <FieldShell label="Tipo de transporte">
                <Select
                  value={form.transport_type}
                  onValueChange={(v) => patch({ transport_type: v as "stdio" | "http_sse" })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stdio">stdio (comando local)</SelectItem>
                    <SelectItem value="http_sse">HTTP / SSE (URL remota)</SelectItem>
                  </SelectContent>
                </Select>
              </FieldShell>

              {form.transport_type === "stdio" ? (
                <FieldShell label="Comando" description="Comando para iniciar o servidor">
                  <input
                    className="field-shell font-mono text-[var(--text-primary)]"
                    value={form.command}
                    onChange={(e) => patch({ command: e.target.value })}
                    placeholder="npx -y @example/mcp-server"
                  />
                </FieldShell>
              ) : (
                <FieldShell label="URL" description="Endpoint HTTP/SSE do servidor">
                  <input
                    className="field-shell text-[var(--text-primary)]"
                    value={form.url}
                    onChange={(e) => patch({ url: e.target.value })}
                    placeholder="https://mcp.example.com/sse"
                  />
                </FieldShell>
              )}

              <FieldShell label="Categoria">
                <Select
                  value={form.category}
                  onValueChange={(v) => patch({ category: v as McpCategory })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.entries(MCP_CATEGORY_LABELS) as [McpCategory, string][]).map(
                      ([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
              </FieldShell>

              <FieldShell label="URL de documentacao" description="Opcional">
                <input
                  className="field-shell text-[var(--text-primary)]"
                  value={form.documentation_url}
                  onChange={(e) => patch({ documentation_url: e.target.value })}
                  placeholder="https://docs.example.com"
                />
              </FieldShell>

              <EnvSchemaBuilder
                fields={form.env_fields}
                onChange={(env_fields) => patch({ env_fields })}
              />
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p className="text-xs leading-5 text-[var(--text-quaternary)]">
              {tl("Esse servidor ficara disponivel no catalogo global de integracoes.")}
            </p>

            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="button-shell button-shell--secondary min-w-[8rem]"
              >
                <span>{tl("Cancelar")}</span>
              </button>
              <button
                type="button"
                disabled={!canSave || saving}
                onClick={handleSubmit}
                className="button-shell button-shell--primary min-w-[10rem]"
              >
                <span>
                  {saving
                    ? tl("Salvando...")
                    : isEditing
                      ? tl("Salvar alteracoes")
                      : tl("Adicionar servidor")}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
