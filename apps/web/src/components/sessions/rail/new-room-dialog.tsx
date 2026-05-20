"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Loader2, Search, Users, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AgentGlyph } from "@/components/ui/agent-glyph";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { mutateControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { requestJson } from "@/lib/http-client";
import { queryKeys } from "@/lib/query/keys";
import { cn } from "@/lib/utils";

interface AgentRow {
  id: string;
  status?: string;
}

interface AgentsListResponse {
  items?: AgentRow[];
}

interface NewRoomDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (result: { threadId: string; squadId: string; workspaceId: string }) => void;
}

interface CreateRoomResponse {
  threadId: string;
  squadId: string;
  workspaceId: string;
  warnings?: string[];
}

export function NewRoomDialog({ open, onClose, onCreated }: NewRoomDialogProps) {
  const { t } = useAppI18n();
  const { showToast } = useToast();
  const { agents } = useAgentCatalog();
  const queryClient = useQueryClient();
  const presence = useAnimatedPresence(open, null, { duration: 200 });
  const nameRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const statusQuery = useQuery<AgentsListResponse>({
    queryKey: queryKeys.controlPlane.agents(),
    queryFn: () => requestJson<AgentsListResponse>("/api/control-plane/agents"),
    enabled: open,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  const statusById = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of statusQuery.data?.items ?? []) {
      if (row?.id) map.set(row.id, (row.status || "").toLowerCase());
    }
    return map;
  }, [statusQuery.data?.items]);

  const filteredAgents = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return agents;
    return agents.filter((agent) => {
      return (
        agent.id.toLowerCase().includes(term) ||
        (agent.label || "").toLowerCase().includes(term)
      );
    });
  }, [agents, search]);

  const hasPausedSelected = useMemo(() => {
    return selectedIds.some((id) => statusById.get(id) === "paused");
  }, [selectedIds, statusById]);

  useEffect(() => {
    if (!presence.isVisible) return;
    const timer = window.setTimeout(() => nameRef.current?.focus(), 60);
    return () => window.clearTimeout(timer);
  }, [presence.isVisible]);

  // Reset on close. Tracked in the change callback so we don't tug on state
  // mid-render.
  const handleCancel = useCallback(() => {
    if (submitting) return;
    onClose();
  }, [onClose, submitting]);

  useEffect(() => {
    if (open) return;
    setName("");
    setSearch("");
    setSelectedIds([]);
    setError(null);
    setSubmitting(false);
  }, [open]);

  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, handleCancel);

  const toggleAgent = useCallback((agentId: string) => {
    setSelectedIds((current) => {
      if (current.includes(agentId)) {
        return current.filter((id) => id !== agentId);
      }
      return [...current, agentId];
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(
        t("sessions.room.create.errors.name", undefined),
      );
      return;
    }
    if (selectedIds.length === 0) {
      setError(
        t("sessions.room.create.errors.agents", undefined),
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await mutateControlPlaneDashboardJson<CreateRoomResponse>(
        "/rooms",
        {
          body: {
            name: trimmedName,
            agentIds: selectedIds,
          },
          fallbackError: t("sessions.room.create.error", undefined),
        },
      );
      void queryClient.invalidateQueries({
        queryKey: queryKeys.dashboard.squadsOverview(null),
      });
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "squads"],
      });
      onCreated({
        threadId: result.threadId,
        squadId: result.squadId,
        workspaceId: result.workspaceId,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      showToast(message, "error");
    } finally {
      setSubmitting(false);
    }
  }, [name, onCreated, queryClient, selectedIds, showToast, t]);

  if (!presence.shouldRender) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        data-visible={presence.isVisible}
        onClick={handleCancel}
        aria-hidden
      />
      <div className="app-modal-frame z-[80] overflow-y-auto px-4 py-6 sm:px-6">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="new-room-dialog-title"
          data-visible={presence.isVisible}
          className="app-modal-panel app-modal-anim relative w-full max-w-[28rem] p-5 sm:p-6"
          onClick={(event) => event.stopPropagation()}
        >
          <header className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] bg-[var(--panel-strong)] text-[var(--text-tertiary)]"
              >
                <Users className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>
              <h2
                id="new-room-dialog-title"
                className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]"
              >
                {t("sessions.room.create.title", undefined)}
              </h2>
            </div>
            <button
              type="button"
              onClick={handleCancel}
              aria-label={t("common.close", undefined)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            </button>
          </header>

          <p className="mt-1 text-[var(--font-size-sm)] leading-[1.5] text-[var(--text-tertiary)]">
            {t("sessions.room.create.helper", undefined)}
          </p>

          <label className="mt-5 flex flex-col gap-1.5">
            <span className="text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {t("sessions.room.create.nameLabel", undefined)}
            </span>
            <input
              ref={nameRef}
              type="text"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                if (error) setError(null);
              }}
              placeholder={t("sessions.room.create.namePlaceholder", undefined)}
              maxLength={120}
              className="h-9 w-full rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[var(--font-size-sm)] text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] outline-none transition-[border-color,background-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] focus:border-[color:var(--border-strong)] focus:bg-[var(--panel)] focus:shadow-[0_0_0_1px_var(--border-strong)]"
            />
          </label>

          <div className="mt-4 flex flex-col gap-1.5">
            <span className="text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {t("sessions.room.create.agentsLabel", undefined)}
              {selectedIds.length > 0 ? (
                <span className="ml-1 font-mono text-[var(--text-tertiary)]">
                  · {selectedIds.length}
                </span>
              ) : null}
            </span>
            <label className="flex h-9 w-full items-center gap-2 rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-3 transition-[border-color,background-color,box-shadow] duration-[120ms] focus-within:border-[color:var(--border-strong)] focus-within:bg-[var(--panel)] focus-within:shadow-[0_0_0_1px_var(--border-strong)]">
              <Search
                className="h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)]"
                strokeWidth={1.75}
                aria-hidden
              />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("sessions.room.create.searchAgents", undefined)}
                className="flex-1 bg-transparent text-[var(--font-size-sm)] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
              />
            </label>
            <div className="mt-1 flex max-h-[260px] flex-col gap-0.5 overflow-y-auto rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] p-1">
              {filteredAgents.length === 0 ? (
                <div className="px-3 py-4 text-center text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
                  {t("sessions.room.create.agentsEmpty", undefined)}
                </div>
              ) : (
                filteredAgents.map((agent) => {
                  const checked = selectedIds.includes(agent.id);
                  const isPaused = statusById.get(agent.id) === "paused";
                  return (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => toggleAgent(agent.id)}
                      aria-pressed={checked}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-[var(--radius-panel-sm)] p-2 text-left",
                        "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                        checked
                          ? "bg-[var(--panel-strong)] text-[var(--text-primary)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                      )}
                    >
                      <AgentGlyph
                        agentId={agent.id}
                        color={agent.color}
                        shape="orb"
                        className="h-7 w-7 shrink-0"
                      />
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-[var(--font-size-sm)] font-medium">
                          {agent.label || agent.id}
                        </span>
                        {agent.label && agent.label !== agent.id ? (
                          <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                            {agent.id}
                          </span>
                        ) : null}
                      </div>
                      {isPaused ? (
                        <span
                          aria-label={t("sessions.room.create.pausedLabel", undefined)}
                          className="shrink-0 rounded-[var(--radius-chip)] bg-[var(--tone-warning-bg)] px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--tone-warning-text)]"
                        >
                          {t("sessions.room.create.pausedBadge", undefined)}
                        </span>
                      ) : null}
                      <span
                        aria-hidden
                        className={cn(
                          "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border",
                          checked
                            ? "border-[color:var(--accent)] bg-[var(--accent)] text-[var(--accent-text)]"
                            : "border-[color:var(--border-strong)] bg-transparent",
                        )}
                      >
                        {checked ? (
                          <Check className="h-3 w-3" strokeWidth={2.5} />
                        ) : null}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
            {selectedIds.length > 0 ? (
              <p className="mt-1 text-[0.6875rem] text-[var(--text-quaternary)]">
                {t("sessions.room.create.coordinatorHint", undefined)}
              </p>
            ) : null}
            {hasPausedSelected ? (
              <p className="mt-1 text-[0.6875rem] text-[var(--tone-warning-text)]">
                {t("sessions.room.create.pausedHint", undefined)}
              </p>
            ) : null}
          </div>

          {error ? (
            <p className="mt-3 text-[var(--font-size-sm)] text-[var(--tone-danger-dot)]">
              {error}
            </p>
          ) : null}

          <div className="mt-6 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={submitting}
              className="inline-flex h-9 items-center justify-center rounded-[var(--radius-panel-sm)] px-3.5 text-[var(--font-size-sm)] font-medium text-[var(--text-secondary)] transition-colors duration-[120ms] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] disabled:opacity-60"
            >
              {t("common.cancel", undefined)}
            </button>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={submitting || !name.trim() || selectedIds.length === 0}
              className={cn(
                "inline-flex h-9 items-center justify-center gap-1.5 rounded-[var(--radius-panel-sm)] px-3.5 text-[var(--font-size-sm)] font-medium",
                "bg-[var(--accent)] text-[var(--accent-text)] transition-[background-color,color] duration-[120ms] hover:bg-[var(--accent-hover)]",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
                "disabled:bg-[var(--panel-strong)] disabled:text-[var(--text-quaternary)]",
              )}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
                  {t("sessions.room.create.creating", undefined)}
                </>
              ) : (
                t("sessions.room.create.confirm", undefined)
              )}
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
