"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { createPortal } from "react-dom";
import { Check, X, Lock } from "lucide-react";
import { AsyncActionButton, InlineSpinner } from "@/components/ui/async-feedback";
import { SecretInput } from "@/components/ui/secret-controls";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson, requestJsonAllowError } from "@/lib/http-client";
import { translate } from "@/lib/i18n";
import {
  parseChannelGatewayState,
  type ChannelGatewayState,
  type ChannelUnknownSender,
} from "@/lib/contracts/channel-gateway";
import {
  type ChannelDefinition,
  type ChannelStatus,
} from "./channel-catalog-data";
import { renderChannelLogo } from "./channel-connection-area";

/*  Tag input for multi-value fields (e.g., allowed user IDs)          */

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

export function ChannelGatewayMiniPanel({ agentId }: { agentId: string }) {
  const { t, tl } = useAppI18n();
  const [state, setState] = useState<ChannelGatewayState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    const payload = await requestJson<unknown>(
      `/api/control-plane/agents/${encodeURIComponent(agentId)}/channels/gateway`,
    );
    setState(parseChannelGatewayState(payload));
  }, [agentId]);

  useEffect(() => {
    refresh().catch((err) => {
      setError(err instanceof Error ? err.message : t("generated.controlPlane.erro_ao_carregar_gateway_b44f49b9"));
    });
  }, [refresh, t, tl]);

  async function runAction(action: string, identityId?: string) {
    setBusy(`${action}:${identityId ?? "new"}`);
    setError(null);
    try {
      if (action === "pairing") {
        await requestJson(
          `/api/control-plane/agents/${encodeURIComponent(agentId)}/channels/gateway/pairing-codes`,
          { method: "POST", body: JSON.stringify({ channel_type: "telegram" }) },
        );
      } else if (identityId) {
        await requestJson(
          `/api/control-plane/agents/${encodeURIComponent(agentId)}/channels/gateway/identities/${encodeURIComponent(identityId)}/${action}`,
          { method: "POST", body: JSON.stringify({}) },
        );
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("generated.controlPlane.acao_do_gateway_falhou_1f773d05"));
    } finally {
      setBusy(null);
    }
  }

  async function revoke(identityId: string) {
    setBusy(`revoke:${identityId}`);
    setError(null);
    try {
      await requestJson(
        `/api/control-plane/agents/${encodeURIComponent(agentId)}/channels/gateway/identities/${encodeURIComponent(identityId)}`,
        { method: "DELETE" },
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("generated.controlPlane.acao_do_gateway_falhou_1f773d05"));
    } finally {
      setBusy(null);
    }
  }

  const pending = state?.unknown_senders ?? [];
  const allowed = (state?.identities ?? []).filter((identity) => identity.status === "allowed");
  const activeCode = state?.pairing_codes?.[0]?.code;

  return (
    <section className="border-t border-[color:var(--divider-hair)] pt-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
            {t("generated.controlPlane.gateway_de_canal_aa1c5785")}
          </div>
          <p className="mt-0.5 text-[11px] text-[var(--text-quaternary)]">
            {t("generated.controlPlane.unknown_senders_ficam_bloqueados_ate_aprovac_f110e376")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => runAction("pairing")}
          disabled={busy !== null}
          aria-label={busy === "pairing:new" ? t("generated.controlPlane.gerando_f053245f") : undefined}
          aria-busy={busy === "pairing:new" || undefined}
          className="inline-flex min-w-28 items-center justify-center rounded-lg bg-[var(--surface-hover)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-elevated)] disabled:opacity-60"
        >
          {busy === "pairing:new" ? (
            <InlineSpinner className="h-3.5 w-3.5" />
          ) : (
            t("generated.controlPlane.pairing_code_1a960f94")
          )}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2">
          <div className="text-[var(--text-quaternary)]">{t("generated.controlPlane.aprovados_82126cab")}</div>
          <div className="mt-1 font-medium text-[var(--text-primary)]">{state?.summary.allowed ?? 0}</div>
        </div>
        <div className="rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2">
          <div className="text-[var(--text-quaternary)]">{t("generated.controlPlane.pendentes_f87ac295")}</div>
          <div className="mt-1 font-medium text-[var(--text-primary)]">{state?.summary.pending ?? 0}</div>
        </div>
        <div className="rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2">
          <div className="text-[var(--text-quaternary)]">{t("generated.controlPlane.pairing_95dc72bd")}</div>
          <div className="mt-1 font-medium text-[var(--text-primary)]">{activeCode ?? "-"}</div>
        </div>
      </div>

      {pending.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5">
          {pending.slice(0, 3).map((sender: ChannelUnknownSender) => (
            <div
              key={sender.identity_id}
              className="flex items-center gap-2 rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-[var(--text-primary)]">
                  {sender.display_name || sender.user_id}
                </div>
                <div className="truncate text-[var(--text-quaternary)]">
                  {sender.user_id} · {sender.message_preview}
                </div>
              </div>
              <button
                type="button"
                onClick={() => runAction("approve", sender.identity_id)}
                disabled={busy !== null}
                className="rounded-md px-2 py-1 text-[11px] text-[var(--tone-success-text)] hover:bg-[var(--tone-success-bg)] disabled:opacity-60"
              >
                {t("generated.controlPlane.aprovar_eca28cca")}
              </button>
              <button
                type="button"
                onClick={() => runAction("block", sender.identity_id)}
                disabled={busy !== null}
                className="rounded-md px-2 py-1 text-[11px] text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg)] disabled:opacity-60"
              >
                {t("generated.controlPlane.bloquear_ca99f1e4")}
              </button>
            </div>
          ))}
        </div>
      )}

      {allowed.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5">
          {allowed.slice(0, 3).map((identity) => (
            <div
              key={identity.identity_id}
              className="flex items-center gap-2 rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-[var(--text-primary)]">
                  {identity.display_name || identity.user_id}
                </div>
                <div className="truncate text-[var(--text-quaternary)]">
                  {identity.user_id} · {identity.source}
                </div>
              </div>
              <button
                type="button"
                onClick={() => revoke(identity.identity_id)}
                disabled={busy !== null}
                className="rounded-md px-2 py-1 text-[11px] text-[var(--text-quaternary)] hover:bg-[var(--surface-hover)] disabled:opacity-60"
              >
                {t("generated.controlPlane.revogar_5c086667")}
              </button>
            </div>
          ))}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-[var(--tone-danger-text)]">{error}</p>}
    </section>
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

/*  Modal                                                              */

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
  const { t } = useAppI18n();
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
      setError(t("generated.controlPlane.preencha_todos_os_campos_obrigatorios_c38649d8"));
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
        setError(result.error ?? validateError ?? t("generated.controlPlane.falha_na_validacao_das_credenciais_400bdf60"));
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("generated.controlPlane.erro_ao_conectar_69bb5811"),
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
        err instanceof Error ? err.message : t("generated.controlPlane.erro_ao_desconectar_e99b0b0f"),
      );
    } finally {
      setDisconnecting(false);
    }
  }

  if (typeof document === "undefined") return null;

  const logo = renderChannelLogo(channel.logoKey, "h-7 w-7");
  const channelLabel = t(channel.labelKey);
  const channelTagline = t(channel.taglineKey);

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="app-modal-frame z-[80] p-4">
        <div
          className="app-modal-panel app-modal-anim relative w-full max-w-lg overflow-hidden border-[var(--border-strong)]"
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
            aria-label={t("generated.controlPlane.fechar_c6eec751")}
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
                  {channelLabel}
                </h3>
                <p className="text-xs text-[var(--text-quaternary)]">
                  {channelTagline}
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
                      {localAgentInfo.username ? `@${localAgentInfo.username}` : t("generated.controlPlane.conectado_e04915ac")}
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
                      {t("generated.controlPlane.usuarios_com_acesso_063979e6")}
                    </div>
                    {loadedAllowedUsers && editingUserIds === null && (
                      <button
                        type="button"
                        onClick={() => setEditingUserIds(allowedUsers.map((u) => u.id).join(","))}
                        className="text-[11px] text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-primary)]"
                      >
                        {t("generated.controlPlane.editar_28e2e08e")}
                      </button>
                    )}
                  </div>

                  {!loadedAllowedUsers ? (
                    <div
                      className="flex items-center gap-2 py-2"
                      role="status"
                      aria-label={t("generated.controlPlane.carregando_62b04e95")}
                    >
                      <InlineSpinner className="h-3.5 w-3.5 text-[var(--text-quaternary)]" />
                    </div>
                  ) : editingUserIds !== null ? (
                    <div className="flex flex-col gap-2">
                      <TagsInput
                        value={editingUserIds}
                        onChange={setEditingUserIds}
                        placeholder={t("generated.controlPlane.digite_o_id_e_pressione_enter_5f36b2ab")}
                        draftRef={userIdsDraftRef}
                      />
                      <p className="text-[11px] text-[var(--text-quaternary)]">
                        {t("generated.controlPlane.deixe_vazio_para_bloquear_todos_ate_aprovar__81d20d6b")}
                      </p>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setEditingUserIds(null)}
                          className="rounded-lg px-3 py-1.5 text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--text-primary)]"
                        >
                          {t("generated.controlPlane.cancelar_091200fb")}
                        </button>
                        <button
                          type="button"
                          disabled={savingUserIds}
                          aria-label={savingUserIds ? t("generated.controlPlane.salvando_b58cece2") : undefined}
                          aria-busy={savingUserIds || undefined}
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
                              setError(t("generated.controlPlane.erro_ao_salvar_usuarios_05eb6044"));
                            } finally {
                              setSavingUserIds(false);
                            }
                          }}
                          className="inline-flex min-w-16 items-center justify-center rounded-lg bg-[var(--surface-hover)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-elevated)]"
                        >
                          {savingUserIds ? (
                            <InlineSpinner className="h-3.5 w-3.5" />
                          ) : (
                            t("generated.controlPlane.salvar_94c457df")
                          )}
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
                              {user.name || t("generated.controlPlane.usuario_4c5adc5f")}
                            </div>
                            <div className="truncate text-[11px] text-[var(--text-quaternary)]">
                              {translate("generated.controlPlane.id_823f6f82")}{user.id}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-lg bg-[var(--surface-elevated-soft)] px-3 py-2 text-xs text-[var(--text-quaternary)]">
                      {t("generated.controlPlane.nenhum_usuario_legado_aprovado_use_o_gateway_37b8bcd9")}
                    </div>
                  )}
                </div>

                {channel.key === "telegram" && <ChannelGatewayMiniPanel agentId={agentId} />}

                {/* Disconnect — subtle text link */}
                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                  aria-label={disconnecting ? t("generated.controlPlane.desconectando_af25b81e") : undefined}
                  aria-busy={disconnecting || undefined}
                  className="inline-flex min-h-5 min-w-20 items-center justify-center self-end text-xs text-[var(--text-quaternary)] transition-colors hover:text-[var(--tone-danger-text)]"
                >
                  {disconnecting ? (
                    <InlineSpinner className="h-3.5 w-3.5" />
                  ) : (
                    t("generated.controlPlane.desconectar_d1a164af")
                  )}
                </button>
              </div>
            ) : (
              /* ---- Disconnected state ---- */
              <div className="flex flex-col gap-4">
                {channel.fields.map((field) => {
                  const fieldLabel = t(field.labelKey);
                  const fieldHelpText = field.helpTextKey ? t(field.helpTextKey) : undefined;
                  return field.type === "tags" ? (
                    <div key={field.key} className="flex flex-col gap-2 px-1 py-1">
                      <div className="flex min-h-[3.1rem] flex-col">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                          {fieldLabel}
                        </div>
                        {fieldHelpText && (
                          <p className="mt-0.5 max-w-[42rem] text-[11px] leading-snug text-[var(--text-quaternary)]">
                            {fieldHelpText}
                          </p>
                        )}
                      </div>
                      <TagsInput
                        value={fieldValues[field.key] ?? ""}
                        onChange={(v) => {
                          setFieldValues((prev) => ({ ...prev, [field.key]: v }));
                          setError(null);
                        }}
                        placeholder={t("generated.controlPlane.digite_e_pressione_enter_a2bf9a1f")}
                      />
                    </div>
                  ) : (
                    <FieldShell
                      key={field.key}
                      label={fieldLabel}
                      description={fieldHelpText}
                    >
                      {field.type === "secret" ? (
                        <SecretInput
                          value={fieldValues[field.key] ?? ""}
                          onChange={(e) => {
                            setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }));
                            setError(null);
                          }}
                          placeholder={t("generated.controlPlane.cole_o_valor_aqui_a94321b7")}
                        />
                      ) : (
                        <input
                          type="text"
                          value={fieldValues[field.key] ?? ""}
                          onChange={(e) => {
                            setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }));
                            setError(null);
                          }}
                          placeholder={t("generated.controlPlane.digite_o_valor_aqui_084a14a7")}
                          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] focus:border-[var(--border-strong)] focus:outline-none"
                        />
                      )}
                    </FieldShell>
                  );
                })}

                {channel.key === "telegram" && <ChannelGatewayMiniPanel agentId={agentId} />}

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
                  loadingLabel={t("generated.controlPlane.validando_e1031e1a")}
                  className="w-full rounded-xl px-4 py-2.5 text-sm font-semibold text-[var(--interactive-active-text)]"
                  style={{
                    background: "linear-gradient(180deg, var(--interactive-active-top), var(--interactive-active-bottom))",
                    border: "1px solid var(--interactive-active-border)",
                  }}
                >
                  {t("generated.controlPlane.validar_e_conectar_16aa616f")}
                </AsyncActionButton>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center gap-1.5 border-t border-[var(--border-subtle)] px-6 py-3 text-xs text-[var(--text-quaternary)]">
            <Lock size={11} />
            <span>{t("generated.controlPlane.credenciais_criptografadas_657054e7")}</span>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
