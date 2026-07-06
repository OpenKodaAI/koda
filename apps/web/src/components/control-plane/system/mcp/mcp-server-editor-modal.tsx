"use client";

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { X, Plus, Trash2 } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { InlineSpinner } from "@/components/ui/async-feedback";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { translate } from "@/lib/i18n";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { McpServerCatalogEntry, McpEnvSchemaField } from "@/lib/control-plane";
import {
  MCP_CATEGORY_KEYS,
  MCP_CATEGORY_LABELS,
  isReservedMcpServerKey,
  type McpCategory,
} from "./mcp-catalog-utils";

/*  Types                                                              */

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

/*  Env Schema Builder                                                 */

function EnvSchemaBuilder({
  fields,
  onChange,
}: {
  fields: EnvFieldDraft[];
  onChange: (fields: EnvFieldDraft[]) => void;
}) {
  const { t } = useAppI18n();

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
          {t("generated.controlPlane.variaveis_de_ambiente_0ff6bf11")}
        </span>
        <button
          type="button"
          onClick={() => onChange([...fields, emptyEnvField()])}
          className="button-shell button-shell--secondary button-shell--sm gap-1 px-3"
        >
          <Plus size={12} />
          <span>{t("generated.controlPlane.adicionar_07558363")}</span>
        </button>
      </div>

      {fields.length === 0 ? (
        <p className="text-xs text-[var(--text-quaternary)]">
          {t("generated.controlPlane.nenhuma_variavel_de_ambiente_configurada_df427661")}
        </p>
      ) : (
        <div className="space-y-2">
          {fields.map((field) => (
            <div
              key={field._id}
              className="flex items-start gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] p-3"
            >
              <div className="grid flex-1 grid-cols-2 gap-2">
                <Input
                  sizeVariant="sm"
                  value={field.key}
                  onChange={(e) =>
                    updateField(field._id, {
                      key: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""),
                    })
                  }
                  placeholder="CHAVE"
                />
                <Input
                  sizeVariant="sm"
                  value={field.label}
                  onChange={(e) => updateField(field._id, { label: e.target.value })}
                  placeholder={t("generated.controlPlane.rotulo_26e3218d")}
                />
              </div>
              <label className="flex items-center gap-1 whitespace-nowrap pt-1.5 text-[10px] text-[var(--text-quaternary)]">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={() => updateField(field._id, { required: !field.required })}
                  className="accent-[var(--interactive-active-border)]"
                />
                {t("generated.controlPlane.obrigatorio_9b9b69aa")}
              </label>
              <button
                type="button"
                onClick={() => removeField(field._id)}
                className="shrink-0 rounded border border-transparent p-1 text-[var(--tone-danger-text)] transition-colors hover:border-[var(--tone-danger-border)] hover:bg-[var(--tone-danger-bg)]"
                aria-label={t("generated.controlPlane.remover_campo_d0d115ea")}
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

/*  Editor Modal                                                       */

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
  const { t } = useAppI18n();
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
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] overflow-y-auto px-4 py-6 sm:px-6">
        <div
          className="app-modal-panel app-modal-anim relative flex max-h-[min(86vh,58rem)] w-full max-w-2xl flex-col overflow-hidden"
          role="dialog"
          aria-modal="true"
          aria-labelledby="mcp-editor-modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={t("generated.controlPlane.fechar_modal_1b5b2901")}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-5 py-5 pr-14 sm:px-6 sm:pr-16">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                {isEditing ? t("generated.controlPlane.servidor_mcp_d8982da2") : t("generated.controlPlane.novo_servidor_mcp_604453c4")}
              </p>
              <h3
                id="mcp-editor-modal-title"
                className="text-[1.15rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)] sm:text-[1.2rem]"
              >
                {isEditing
                  ? t("generated.controlPlane.editar_servidor_mcp_560c29f3")
                  : t("generated.controlPlane.adicionar_servidor_mcp_ea88d544")}
              </h3>
              <p className="max-w-[38rem] text-sm leading-6 text-[var(--text-quaternary)]">
                {t("generated.controlPlane.configure_a_conexao_global_com_um_servidor_m_c5460c06")}
              </p>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6 sm:py-6">
            <div className="space-y-4">
              <FieldShell
                label={t("generated.controlPlane.identificador_slug_72353c57")}
                description={
                  isReservedServerKey
                    ? t("generated.controlPlane.este_identificador_e_reservado_e_nao_pode_se_1fe967e8")
                    : t("generated.controlPlane.chave_unica_do_servidor_c56db6e1")
                }
              >
                <Input
                  value={form.server_key}
                  onChange={(e) => patch({ server_key: e.target.value })}
                  placeholder={translate("generated.controlPlane.meu_servidor_429b287a")}
                  disabled={isEditing || lockServerKey}
                  invalid={isReservedServerKey}
                />
              </FieldShell>

              <FieldShell label={t("generated.controlPlane.nome_de_exibicao_db9dfcf3")}>
                <Input
                  value={form.display_name}
                  onChange={(e) => patch({ display_name: e.target.value })}
                  placeholder={t("generated.controlPlane.meu_servidor_mcp_701fba25")}
                />
              </FieldShell>

              <FieldShell label={t("generated.controlPlane.descricao_ff40fdea")}>
                <Textarea
                  rows={3}
                  className="min-h-[60px]"
                  value={form.description}
                  onChange={(e) => patch({ description: e.target.value })}
                  placeholder={t("generated.controlPlane.breve_descricao_do_que_esse_servidor_oferece_45c203f6")}
                />
              </FieldShell>

              <FieldShell label={t("generated.controlPlane.tipo_de_transporte_3dd37bf3")}>
                <Select
                  value={form.transport_type}
                  onValueChange={(v) => patch({ transport_type: v as "stdio" | "http_sse" })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stdio">{t("generated.controlPlane.stdio_comando_local_79f041b1")}</SelectItem>
                    <SelectItem value="http_sse">{t("generated.controlPlane.http_sse_url_remota_e771b2de")}</SelectItem>
                  </SelectContent>
                </Select>
              </FieldShell>

              {form.transport_type === "stdio" ? (
                <FieldShell label={t("generated.controlPlane.comando_b21ea3ed")} description={t("generated.controlPlane.comando_para_iniciar_o_servidor_a53b86ce")}>
                  <Input
                    className="font-mono"
                    value={form.command}
                    onChange={(e) => patch({ command: e.target.value })}
                    placeholder={translate("generated.controlPlane.npx_y_example_mcp_server_9d26dab2")}
                  />
                </FieldShell>
              ) : (
                <FieldShell label={t("generated.controlPlane.url_54547d35")} description={t("generated.controlPlane.endpoint_http_sse_do_servidor_d651e5af")}>
                  <Input
                    value={form.url}
                    onChange={(e) => patch({ url: e.target.value })}
                    placeholder="https://mcp.example.com/sse"
                  />
                </FieldShell>
              )}

              <FieldShell label={t("generated.controlPlane.categoria_d4679e28")}>
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
                          {t(MCP_CATEGORY_KEYS[value], { defaultValue: label })}
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
              </FieldShell>

              <FieldShell label={t("generated.controlPlane.url_de_documentacao_499c2a35")} description={t("generated.controlPlane.opcional_f6c7765c")}>
                <Input
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
              {t("generated.controlPlane.esse_servidor_ficara_disponivel_no_catalogo__138cb47f")}
            </p>

            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="button-shell button-shell--secondary min-w-[8rem]"
              >
                <span>{t("generated.controlPlane.cancelar_091200fb")}</span>
              </button>
              <button
                type="button"
                disabled={!canSave || saving}
                onClick={handleSubmit}
                aria-label={saving ? t("generated.controlPlane.salvando_b58cece2") : undefined}
                aria-busy={saving || undefined}
                className="button-shell button-shell--primary min-w-[10rem]"
              >
                {saving ? <InlineSpinner className="h-4 w-4" /> : null}
                <span>{isEditing ? t("generated.controlPlane.salvar_alteracoes_4cadc5e7") : t("generated.controlPlane.adicionar_servidor_5ad219d2")}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
