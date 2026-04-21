"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { createPortal } from "react-dom";
import { Check, X, Lock } from "lucide-react";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { SecretInput } from "@/components/ui/secret-controls";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson, requestJsonAllowError } from "@/lib/http-client";
import {
  type ChannelDefinition,
  type ChannelStatus,
} from "./channel-catalog-data";
import { renderChannelLogo } from "./channel-connection-area";

/* ------------------------------------------------------------------ */
/*  Tag input for multi-value fields (e.g., allowed user IDs)          */
/* ------------------------------------------------------------------ */

function TagsInput({
  value,
  onChange,
  placeholder,
  draftRef,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  draftRef?: MutableRefObject<string>;
}) {
  const tags = useMemo(
    () => (value ? value.split(",").map((t) => t.trim()).filter(Boolean) : []),
    [value],
  );
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (draftRef) draftRef.current = draft;
  }, [draft, draftRef]);

  const addTag = useCallback(
    (raw: string) => {
      const clean = raw.trim().replace(/,/g, "");
      if (!clean || tags.includes(clean)) return;
      onChange([...tags, clean].join(","));
    },
    [tags, onChange],
  );

  const removeTag = useCallback(
    (idx: number) => {
      onChange(tags.filter((_, i) => i !== idx).join(","));
    },
    [tags, onChange],
  );

  return (
    <div className="flex min-h-[38px] flex-wrap items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1.5">
      {tags.map((tag, i) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-md bg-[var(--surface-hover)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]"
        >
          {tag}
          <button
            type="button"
            onClick={() => removeTag(i)}
            className="ml-0.5 text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-primary)]"
          >
            <X size={10} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === ",") && draft.trim()) {
            e.preventDefault();
            addTag(draft);
            setDraft("");
          }
          if (e.key === "Backspace" && !draft && tags.length > 0) {
            removeTag(tags.length - 1);
          }
        }}
        onBlur={() => {
          if (draft.trim()) {
            addTag(draft);
            setDraft("");
          }
        }}
        placeholder={tags.length === 0 ? placeholder : ""}
        style={{ outline: "none", boxShadow: "none", border: "none" }}
        className="min-w-[80px] flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
        autoComplete="off"
        data-1p-ignore
        data-lpignore="true"
      />
    </div>
  );
}

type ValidateResponse = {
  ok: boolean;
  display_name?: string;
  display_id?: string;
  // Legacy telegram-specific fields for backward compat
  bot_username?: string;
  bot_name?: string;
  error?: string;
};

type AgentInfo = { username: string; name: string };

/* ------------------------------------------------------------------ */
/*  Modal                                                              */
/* ------------------------------------------------------------------ */

export function ChannelConnectionModal({
  agentId,
  channel,
  status: initialStatus,
  agentInfo: initialAgentInfo,
  onClose,
  onStatusChange,
}: {
  agentId: string;
  channel: ChannelDefinition;
  status: ChannelStatus;
  agentInfo: AgentInfo | null;
  onClose: () => void;
  onStatusChange: (status: ChannelStatus, agentUsername?: string, agentName?: string) => void;
}) {
  const { tl } = useAppI18n();
  const [fieldValues, setFieldValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of channel.fields) {
      initial[field.key] = "";
    }
    return initial;
  });
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localAgentInfo, setLocalAgentInfo] = useState<AgentInfo | null>(initialAgentInfo);
  const [localStatus, setLocalStatus] = useState<ChannelStatus>(initialStatus);

  const isConnected = localStatus === "connected";
  const [loadingAgentInfo, setLoadingAgentInfo] = useState(false);
  const [allowedUsers, setAllowedUsers] = useState<{ id: string; name: string }[]>([]);
  const [loadedAllowedUsers, setLoadedAllowedUsers] = useState(false);
  const [editingUserIds, setEditingUserIds] = useState<string | null>(null);
  const [savingUserIds, setSavingUserIds] = useState(false);
  const userIdsDraftRef = useRef<string>("");
  const statusUrl = `/api/channels/${encodeURIComponent(agentId)}/${channel.key}/status`;

  /* ---- Fetch agent info when connected but missing ---- */
  useEffect(() => {
    if (!isConnected || localAgentInfo || loadingAgentInfo) return;
    setLoadingAgentInfo(true);
    fetch(statusUrl, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) return;
        const username = data.display_id ?? data.bot_username;
        const name = data.display_name ?? data.bot_name ?? "";
        if (username) {
          setLocalAgentInfo({ username, name });
          onStatusChange("connected", username, name);
        }
        if (Array.isArray(data.allowed_users)) {
          setAllowedUsers(data.allowed_users);
          setLoadedAllowedUsers(true);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingAgentInfo(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, localAgentInfo, agentId, channel.key]);

  /* ---- Always fetch allowed users when connected (even if agent info was cached) ---- */
  useEffect(() => {
    if (!isConnected || loadedAllowedUsers) return;
    fetch(statusUrl, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) return;
        if (Array.isArray(data.allowed_users)) {
          setAllowedUsers(data.allowed_users);
        }
        setLoadedAllowedUsers(true);
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, loadedAllowedUsers]);

  /* ---- Escape to close ---- */
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

  /* ---- Prevent body scroll ---- */
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
      setFieldValues(() => {
        const cleared: Record<string, string> = {};
        for (const field of channel.fields) {
          cleared[field.key] = "";
        }
        return cleared;
      });
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- Connect handler ---- */
  async function handleConnect() {
    // Validate all required fields are filled
    const requiredFields = channel.fields.filter((f) => f.required);
    const emptyField = requiredFields.find((f) => !fieldValues[f.key]?.trim());
    if (emptyField) {
      setError(tl("Preencha todos os campos obrigatórios."));
      return;
    }

    setConnecting(true);
    setError(null);

    try {
      // Store all secrets/values (including tags as comma-separated strings)
      for (const field of channel.fields) {
        const value = fieldValues[field.key]?.trim();
        if (!value) continue;
        await requestJson(
          `/api/control-plane/agents/${agentId}/secrets/${field.key}?scope=agent`,
          {
            method: "PUT",
            body: JSON.stringify({ value }),
          },
        );
      }

      // Validate via channel-specific endpoint
      const credentials = Object.fromEntries(
        channel.fields.filter((f) => f.type !== "tags").map((f) => [f.key, fieldValues[f.key]?.trim() ?? ""]),
      );
      const { ok, data, error: validateError } = await requestJsonAllowError<ValidateResponse>(
        `/api/channels/${agentId}/${channel.key}/validate`,
        {
          method: "POST",
          body: JSON.stringify({ credentials }),
        },
      );

      const result = data ?? { ok: false };
      if (ok && result.ok) {
        const info = {
          username: result.display_id ?? result.bot_username ?? "",
          name: result.display_name ?? result.bot_name ?? "",
        };
        setLocalAgentInfo(info);
        setLocalStatus("connected");
        onStatusChange("connected", info.username, info.name);
      } else {
        setError(result.error ?? validateError ?? tl("Falha na validação das credenciais."));
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : tl("Erro ao conectar."),
      );
    } finally {
      setConnecting(false);
    }
  }

  /* ---- Disconnect handler ---- */
  async function handleDisconnect() {
    setDisconnecting(true);
    setError(null);

    try {
      // Delete ALL secrets for this channel
      for (const field of channel.fields) {
        await requestJson(
          `/api/control-plane/agents/${agentId}/secrets/${field.key}?scope=agent`,
          { method: "DELETE" },
        );
      }
      setLocalAgentInfo(null);
      setLocalStatus("disconnected");
      setFieldValues(() => {
        const cleared: Record<string, string> = {};
        for (const field of channel.fields) {
          cleared[field.key] = "";
        }
        return cleared;
      });
      onStatusChange("disconnected");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : tl("Erro ao desconectar."),
      );
    } finally {
      setDisconnecting(false);
    }
  }

  if (typeof document === "undefined") return null;

  const logo = renderChannelLogo(channel.logoKey, "h-7 w-7");

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel relative w-full max-w-lg overflow-hidden border-[var(--border-strong)]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="channel-modal-title"
          data-connection-modal
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            className="app-surface-close"
            aria-label={tl("Fechar")}
          >
            <X className="h-4 w-4" />
          </button>

          {/* Header */}
          <div className="px-6 py-5 pr-14">
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl"
                style={{ backgroundColor: channel.gradientFrom }}
              >
                <span style={{ color: "#ffffff" }}>{logo}</span>
              </div>
              <div>
                <h3
                  id="channel-modal-title"
                  className="text-base font-semibold text-[var(--text-primary)]"
                >
                  {channel.label}
                </h3>
                <p className="text-xs text-[var(--text-quaternary)]">
                  {tl(channel.tagline)}
                </p>
              </div>
            </div>
          </div>

          {/* Body */}
          <div className="px-6 pb-5">
            {isConnected && loadingAgentInfo ? (
              /* ---- Loading agent info ---- */
              <div className="flex items-center justify-center py-6">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--text-primary)]" />
              </div>
            ) : isConnected && localAgentInfo ? (
              /* ---- Connected state ---- */
              <div className="flex flex-col gap-4">
                <div
                  className="flex items-center gap-3 rounded-xl px-4 py-3"
                  style={{ backgroundColor: "rgba(113,219,190,0.08)" }}
                >
                  <div
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                    style={{ backgroundColor: "rgba(113,219,190,0.15)" }}
                  >
                    <Check size={16} style={{ color: "var(--tone-success-dot)" }} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      {localAgentInfo.username ? `@${localAgentInfo.username}` : tl("Conectado")}
                    </div>
                    {localAgentInfo.name && (
                      <div className="text-xs text-[var(--text-tertiary)]">
                        {localAgentInfo.name}
                      </div>
                    )}
                  </div>
                </div>

                {/* Allowed users */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                      {tl("Usuarios com acesso")}
                    </div>
                    {loadedAllowedUsers && editingUserIds === null && (
                      <button
                        type="button"
                        onClick={() => setEditingUserIds(allowedUsers.map((u) => u.id).join(","))}
                        className="text-[11px] text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-primary)]"
                      >
                        {tl("Editar")}
                      </button>
                    )}
                  </div>

                  {!loadedAllowedUsers ? (
                    <div className="flex items-center gap-2 py-2">
                      <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--text-tertiary)]" />
                      <span className="text-xs text-[var(--text-quaternary)]">{tl("Carregando...")}</span>
                    </div>
                  ) : editingUserIds !== null ? (
                    <div className="flex flex-col gap-2">
                      <TagsInput
                        value={editingUserIds}
                        onChange={setEditingUserIds}
                        placeholder={tl("Digite o ID e pressione Enter")}
                        draftRef={userIdsDraftRef}
                      />
                      <p className="text-[11px] text-[var(--text-quaternary)]">
                        {tl("Deixe vazio para permitir todos.")}
                      </p>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setEditingUserIds(null)}
                          className="rounded-lg px-3 py-1.5 text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-primary)]"
                        >
                          {tl("Cancelar")}
                        </button>
                        <button
                          type="button"
                          disabled={savingUserIds}
                          onClick={async () => {
                            setSavingUserIds(true);
                            try {
                              const committed = editingUserIds
                                .split(",")
                                .map((t) => t.trim())
                                .filter(Boolean);
                              const pending = userIdsDraftRef.current.trim().replace(/,/g, "");
                              if (pending && !committed.includes(pending)) {
                                committed.push(pending);
                              }
                              const value = committed.join(",");
                              if (value) {
                                await requestJson(
                                  `/api/control-plane/agents/${agentId}/secrets/ALLOWED_USER_IDS?scope=agent`,
                                  { method: "PUT", body: JSON.stringify({ value }) },
                                );
                              } else {
                                await requestJson(
                                  `/api/control-plane/agents/${agentId}/secrets/ALLOWED_USER_IDS?scope=agent`,
                                  { method: "DELETE" },
                                ).catch(() => {});
                              }
                              setEditingUserIds(null);
                              setLoadedAllowedUsers(false);
                            } catch {
                              setError(tl("Erro ao salvar usuarios."));
                            } finally {
                              setSavingUserIds(false);
                            }
                          }}
                          className="rounded-lg bg-[var(--surface-hover)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-elevated)]"
                        >
                          {savingUserIds ? tl("Salvando...") : tl("Salvar")}
                        </button>
                      </div>
                    </div>
                  ) : allowedUsers.length > 0 ? (
                    <div className="flex flex-col gap-1.5">
                      {allowedUsers.map((user) => (
                        <div
                          key={user.id}
                          className="flex items-center gap-2.5 rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2"
                        >
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--surface-hover)] text-[10px] font-bold text-[var(--text-tertiary)]">
                            {(user.name?.[0] ?? user.id[0] ?? "?").toUpperCase()}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-xs font-medium text-[var(--text-primary)]">
                              {user.name || tl("Usuario")}
                            </div>
                            <div className="truncate text-[11px] text-[var(--text-quaternary)]">
                              ID: {user.id}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2 text-xs text-[var(--text-quaternary)]">
                      {tl("Todos os usuarios podem interagir com este bot.")}
                    </div>
                  )}
                </div>

                {/* Disconnect — subtle text link */}
                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                  className="self-end text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--tone-danger-text)]"
                >
                  {disconnecting ? tl("Desconectando...") : tl("Desconectar")}
                </button>
              </div>
            ) : (
              /* ---- Disconnected state ---- */
              <div className="flex flex-col gap-4">
                {channel.fields.map((field) =>
                  field.type === "tags" ? (
                    <div key={field.key} className="flex flex-col gap-2 px-1 py-1">
                      <div className="flex min-h-[3.1rem] flex-col">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                          {tl(field.label)}
                        </div>
                        {field.helpText && (
                          <p className="mt-0.5 max-w-[42rem] text-[11px] leading-snug text-[var(--text-quaternary)]">
                            {tl(field.helpText)}
                          </p>
                        )}
                      </div>
                      <TagsInput
                        value={fieldValues[field.key] ?? ""}
                        onChange={(v) => {
                          setFieldValues((prev) => ({ ...prev, [field.key]: v }));
                          setError(null);
                        }}
                        placeholder={tl("Digite e pressione Enter")}
                      />
                    </div>
                  ) : (
                    <FieldShell
                      key={field.key}
                      label={field.label}
                      description={field.helpText ? tl(field.helpText) : undefined}
                    >
                      {field.type === "secret" ? (
                        <SecretInput
                          value={fieldValues[field.key] ?? ""}
                          onChange={(e) => {
                            setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }));
                            setError(null);
                          }}
                          placeholder={tl("Cole o valor aqui")}
                        />
                      ) : (
                        <input
                          type="text"
                          value={fieldValues[field.key] ?? ""}
                          onChange={(e) => {
                            setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }));
                            setError(null);
                          }}
                          placeholder={tl("Digite o valor aqui")}
                          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] focus:border-[var(--border-strong)] focus:outline-none"
                        />
                      )}
                    </FieldShell>
                  ),
                )}

                {/* Error */}
                {error && (
                  <p className="text-sm text-[var(--tone-danger-text)]">
                    {error}
                  </p>
                )}

                {/* Action */}
                <AsyncActionButton
                  type="button"
                  onClick={handleConnect}
                  loading={connecting}
                  status={connecting ? "pending" : "idle"}
                  loadingLabel={tl("Validando")}
                  className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-[var(--interactive-active-text)]"
                  style={{
                    background: "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                    border: "1px solid var(--interactive-active-border)",
                  }}
                >
                  {tl("Validar e conectar")}
                </AsyncActionButton>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center gap-1.5 border-t border-[var(--border-subtle)] px-6 py-3 text-xs text-[var(--text-quaternary)]">
            <Lock size={11} />
            <span>{tl("Credenciais criptografadas")}</span>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
