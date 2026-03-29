"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { LocalizedTree } from "@/components/shared/localized-tree";

/* -------------------------------------------------------------------------- */
/*  Request helper                                                             */
/* -------------------------------------------------------------------------- */

async function requestJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

/* -------------------------------------------------------------------------- */
/*  Tab: Segredos                                                              */
/* -------------------------------------------------------------------------- */

export function TabSegredos() {
  const { state, updateField } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const botId = state.bot.id;
  const secrets = state.bot.secrets ?? [];

  async function handleSaveSecret() {
    const key = state.secretKey.trim();
    const value = state.secretValue.trim();
    const scope = state.secretScope.trim() || "bot";

    if (!key) {
      showToast(tl("A chave do segredo e obrigatoria."), "warning");
      return;
    }
    if (!value) {
      showToast(tl("O valor do segredo e obrigatorio."), "warning");
      return;
    }

    setBusyKey("save");
    try {
      await requestJson(
        `/api/control-plane/agents/${botId}/secrets/${encodeURIComponent(key)}?scope=${encodeURIComponent(scope)}`,
        {
          method: "PUT",
          body: JSON.stringify({ value }),
        },
      );
      showToast(tl('Segredo "{{key}}" salvo.', { key }), "success");
      updateField("secretKey", "");
      updateField("secretValue", "");
      updateField("secretScope", "");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar segredo."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDeleteSecret(key: string, scope: string) {
    setBusyKey(`delete-${key}`);
    try {
      await requestJson(
        `/api/control-plane/agents/${botId}/secrets/${encodeURIComponent(key)}?scope=${encodeURIComponent(scope || "bot")}`,
        { method: "DELETE" },
      );
      showToast(tl('Segredo "{{key}}" removido.', { key }), "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao remover segredo."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <LocalizedTree>
      <div className="glass-card p-6 flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          {tl("Segredos")}
        </h2>
        <p className="text-sm text-[var(--text-tertiary)]">
          {tl("Gerenciamento de secrets — chaves de API, tokens e credenciais.")}
        </p>
      </div>

      {/* Add secret form */}
      <div className="flex flex-col gap-4 p-4 border border-[var(--border-subtle)] rounded">
        <span className="eyebrow">{tl("Novo segredo")}</span>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-[var(--text-tertiary)]">
              {tl("Chave")}
            </span>
            <input
              type="text"
              value={state.secretKey}
              onChange={(e) => updateField("secretKey", e.target.value)}
              className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
              placeholder="OPENAI_API_KEY"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-[var(--text-tertiary)]">
              {tl("Escopo")}
            </span>
            <select
              value={state.secretScope || "bot"}
              onChange={(e) => updateField("secretScope", e.target.value)}
              className="field-shell px-4 py-3 text-sm text-[var(--text-primary)]"
            >
              <option value="bot">{tl("Bot")}</option>
              <option value="global">{tl("Global")}</option>
            </select>
          </label>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-[var(--text-tertiary)]">
            {tl("Valor")}
          </span>
          <textarea
            value={state.secretValue}
            onChange={(e) => updateField("secretValue", e.target.value)}
            className="field-shell w-full px-4 py-3 font-mono text-xs text-[var(--text-primary)] resize-y"
            style={{ minHeight: "80px" }}
            placeholder="sk-..."
            spellCheck={false}
          />
        </label>

        <div className="flex justify-end">
          <button
            type="button"
            className="button-shell button-shell--primary button-shell--sm"
            disabled={busyKey !== null}
            onClick={handleSaveSecret}
          >
            <span>
              {busyKey === "save" ? tl("Salvando...") : tl("Salvar segredo")}
            </span>
          </button>
        </div>
      </div>

      {/* Existing secrets list */}
      <div className="flex flex-col gap-3">
        <span className="eyebrow">
          {tl("Segredos existentes ({{count}})", { count: secrets.length })}
        </span>

        {secrets.length === 0 ? (
          <p className="text-sm text-[var(--text-quaternary)]">
            {tl("Nenhum segredo cadastrado.")}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {secrets.map((secret) => {
              const secretKey = String(secret.key || secret.name || "—");
              const secretScope = String(secret.scope || "bot");
              const preview = secret.preview
                ? String(secret.preview)
                : tl("Mascarado");

              return (
                <div
                  key={`${secretKey}-${secretScope}`}
                  className="flex items-center gap-4 px-4 py-3 border border-[var(--border-subtle)] rounded"
                >
                  <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                    <span className="text-sm font-medium text-[var(--text-primary)] truncate">
                      {secretKey}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="chip text-xs">{secretScope}</span>
                      <span className="text-xs text-[var(--text-quaternary)] font-mono">
                        {preview}
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="shrink-0 p-2 text-[var(--text-quaternary)] hover:text-[var(--tone-danger-text)] transition-colors"
                    disabled={busyKey !== null}
                    onClick={() => handleDeleteSecret(secretKey, secretScope)}
                    aria-label={tl("Delete secret {{key}}", { key: secretKey })}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      </div>
    </LocalizedTree>
  );
}
