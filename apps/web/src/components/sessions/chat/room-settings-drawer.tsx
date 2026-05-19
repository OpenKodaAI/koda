"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  keepPreviousData,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Archive,
  Check,
  ChevronDown,
  Crown,
  Eye,
  LoaderCircle,
  MessageSquare,
  Pause,
  PencilLine,
  Play,
  Plus,
  UserMinus,
  UserRound,
  Users,
} from "lucide-react";
import { AgentGlyph } from "@/components/ui/agent-glyph";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { RoomPhotoEditor } from "@/components/sessions/chat/room-photo-editor";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useToast } from "@/hooks/use-toast";
import {
  fetchControlPlaneDashboardJson,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";
import { requestJson } from "@/lib/http-client";
import { queryKeys } from "@/lib/query/keys";
import type { SquadThreadOverviewResponse } from "@/lib/squads";
import { cn } from "@/lib/utils";

interface RoomSettingsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  threadId: string;
  /** Notified when the user archives the room from settings. */
  onArchived?: () => void;
}

interface RoomSettingsPanelProps {
  threadId: string;
  enabled?: boolean;
  /** Notified when the user archives the room from settings. */
  onArchived?: () => void;
  onClose?: () => void;
  variant?: "drawer" | "rail";
  className?: string;
}

interface AgentRow {
  id: string;
  status?: string;
}

type ParticipantRole = "coordinator" | "worker" | "observer";

const ROLE_OPTIONS: ParticipantRole[] = ["coordinator", "worker", "observer"];

function deriveInitials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "·";
  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function deriveAvatarColor(seed: string): string {
  // Deterministic hue from the seed so the avatar feels stable for a room.
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 36% 32%)`;
}

export function RoomSettingsDrawer({
  open,
  onOpenChange,
  threadId,
  onArchived,
}: RoomSettingsDrawerProps) {
  const { t } = useAppI18n();

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      modal
      title={t("sessions.room.settings.title", { defaultValue: "Info" })}
      width="min(460px, 92vw)"
    >
      <RoomSettingsPanel
        threadId={threadId}
        enabled={open}
        onArchived={onArchived}
        onClose={() => onOpenChange(false)}
      />
    </Drawer>
  );
}

export function RoomSettingsPanel({
  threadId,
  enabled = true,
  onArchived,
  onClose,
  variant = "drawer",
  className,
}: RoomSettingsPanelProps) {
  const { t } = useAppI18n();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { agents } = useAgentCatalog();
  const inline = variant === "rail";

  const detailQuery = useControlPlaneQuery<SquadThreadOverviewResponse>({
    tier: "live",
    queryKey: queryKeys.dashboard.squadThread(threadId),
    enabled,
    refetchInterval: enabled ? 15_000 : false,
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadThreadOverviewResponse>(
        `/squads/threads/${threadId}`,
        {
          signal,
          fallbackError: t("sessions.room.settings.loadError", {
            defaultValue: "Could not load room settings.",
          }),
        },
      ),
  });

  const detail = detailQuery.data ?? null;
  const participants = useMemo(
    () => detail?.participants?.filter((p) => !p.leftAt) ?? [],
    [detail?.participants],
  );

  const agentsListQuery = useQuery<{ items?: AgentRow[] }>({
    queryKey: queryKeys.controlPlane.agents(),
    queryFn: () =>
      requestJson<{ items?: AgentRow[] }>("/api/control-plane/agents"),
    enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  const statusById = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of agentsListQuery.data?.items ?? []) {
      if (row?.id) map.set(row.id, (row.status || "").toLowerCase());
    }
    return map;
  }, [agentsListQuery.data?.items]);

  const labelMap = useMemo(() => {
    const map = new Map<string, { label: string; color: string }>();
    for (const agent of agents) {
      map.set(agent.id, {
        label: agent.label || agent.id,
        color: agent.color,
      });
    }
    return map;
  }, [agents]);

  const labelFor = useCallback(
    (agentId: string) => {
      const meta = labelMap.get(agentId);
      return meta ?? { label: agentId, color: "var(--accent)" };
    },
    [labelMap],
  );

  const participantSet = useMemo(
    () => new Set(participants.map((p) => p.agentId)),
    [participants],
  );
  const candidateAgents = useMemo(
    () => agents.filter((agent) => !participantSet.has(agent.id)),
    [agents, participantSet],
  );

  const [editing, setEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [titleDirty, setTitleDirty] = useState(false);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const [savingMeta, setSavingMeta] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [archivingPending, setArchivingPending] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [showAddPicker, setShowAddPicker] = useState(false);
  const [pendingMutation, setPendingMutation] = useState<string | null>(null);

  // Keep the inline title in sync with server data unless the user is actively
  // editing it. This avoids clobbering typed text during background refreshes.
  useEffect(() => {
    if (!enabled) return;
    if (!detail) return;
    if (titleDirty) return;
    setTitleDraft(detail.thread.title || "");
  }, [detail, enabled, titleDirty]);

  useEffect(() => {
    setPhotoPreviewUrl(null);
  }, [detail?.thread.photoUrl]);

  // Reset transient state when the panel becomes inactive.
  useEffect(() => {
    if (enabled) return;
    setEditing(false);
    setTitleDirty(false);
    setPhotoPreviewUrl(null);
    setArchiveOpen(false);
    setShowAddPicker(false);
  }, [enabled]);

  const invalidateThread = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.dashboard.squadThread(threadId),
    });
    // The rail's `useRooms` hook caches a per-squad thread listing under
    // `queryKeys.dashboard.squadThreads(squadId, null)`. Targeting just the
    // overview misses those entries, leaving the rail thumbnail stale after
    // a rename / photo upload / member edit. Invalidating by the
    // `["dashboard", "squads"]` prefix covers overview + every per-squad
    // listing in one shot.
    void queryClient.invalidateQueries({
      queryKey: ["dashboard", "squads"],
    });
  }, [queryClient, threadId]);

  const showRequestError = useCallback(
    (error: unknown, fallback = "Unknown error") => {
      showToast(error instanceof Error && error.message.trim() ? error.message : fallback, "error");
    },
    [showToast],
  );

  const handleSaveTitle = useCallback(async () => {
    if (savingMeta || !detail) return;
    const nextTitle = titleDraft.trim();
    const currentTitle = (detail?.thread.title ?? "").trim();
    const titleChanged = nextTitle && nextTitle !== currentTitle;
    if (!titleChanged) {
      setTitleDraft(currentTitle);
      setTitleDirty(false);
      return;
    }
    setSavingMeta(true);
    try {
      await mutateControlPlaneDashboardJson(`/squads/threads/${threadId}`, {
        method: "PATCH",
        body: { title: nextTitle },
        fallbackError: t("sessions.room.settings.saveError", {
          defaultValue: "Could not save changes.",
        }),
      });
      invalidateThread();
      setTitleDraft(nextTitle);
      setTitleDirty(false);
    } catch (err) {
      showRequestError(err);
    } finally {
      setSavingMeta(false);
    }
  }, [
    detail,
    invalidateThread,
    savingMeta,
    showRequestError,
    t,
    threadId,
    titleDraft,
  ]);

  const handleTitleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        event.currentTarget.blur();
        return;
      }
      if (event.key === "Escape") {
        setTitleDraft((detail?.thread.title ?? "").trim());
        setTitleDirty(false);
        event.currentTarget.blur();
      }
    },
    [detail?.thread.title],
  );

  const handleSetRole = useCallback(
    async (agentId: string, nextRole: ParticipantRole) => {
      if (pendingMutation) return;
      setPendingMutation(`role:${agentId}`);
      try {
        await mutateControlPlaneDashboardJson(
          `/squads/threads/${threadId}/participants/${encodeURIComponent(agentId)}`,
          {
            method: "PATCH",
            body: { role: nextRole },
            fallbackError: t("sessions.room.settings.roleError", {
              defaultValue: "Could not change role.",
            }),
          },
        );
        invalidateThread();
      } catch (err) {
        showRequestError(err);
      } finally {
        setPendingMutation(null);
      }
    },
    [invalidateThread, pendingMutation, showRequestError, t, threadId],
  );

  const handleRemove = useCallback(
    async (agentId: string) => {
      if (pendingMutation) return;
      setPendingMutation(`remove:${agentId}`);
      try {
        await mutateControlPlaneDashboardJson(
          `/squads/threads/${threadId}/participants/${encodeURIComponent(agentId)}`,
          {
            method: "DELETE",
            fallbackError: t("sessions.room.settings.removeError", {
              defaultValue: "Could not remove agent.",
            }),
          },
        );
        invalidateThread();
      } catch (err) {
        showRequestError(err);
      } finally {
        setPendingMutation(null);
      }
    },
    [invalidateThread, pendingMutation, showRequestError, t, threadId],
  );

  const handleAdd = useCallback(
    async (agentId: string) => {
      if (pendingMutation) return;
      setPendingMutation(`add:${agentId}`);
      try {
        await mutateControlPlaneDashboardJson(
          `/squads/threads/${threadId}/participants`,
          {
            method: "POST",
            body: { agentId, role: "worker" },
            fallbackError: t("sessions.room.settings.addError", {
              defaultValue: "Could not add agent.",
            }),
          },
        );
        invalidateThread();
        setShowAddPicker(false);
      } catch (err) {
        showRequestError(err);
      } finally {
        setPendingMutation(null);
      }
    },
    [invalidateThread, pendingMutation, showRequestError, t, threadId],
  );

  const handleArchive = useCallback(async () => {
    if (archivingPending) return;
    setArchivingPending(true);
    try {
      await mutateControlPlaneDashboardJson(`/squads/threads/${threadId}`, {
        method: "DELETE",
        fallbackError: t("sessions.room.settings.archiveError", {
          defaultValue: "Could not archive room.",
        }),
      });
      invalidateThread();
      setArchiveOpen(false);
      onArchived?.();
      onClose?.();
    } catch (err) {
      showRequestError(err);
    } finally {
      setArchivingPending(false);
    }
  }, [archivingPending, invalidateThread, onArchived, onClose, showRequestError, t, threadId]);

  const status = detail?.thread.status;
  const isPaused = status === "paused";
  const handleTogglePause = useCallback(async () => {
    if (!detail || pausing) return;
    if (status !== "open" && status !== "paused") {
      showToast(
        t("sessions.room.settings.pauseUnavailable", {
          defaultValue: "Pause is only available for active rooms.",
        }),
        "warning",
      );
      return;
    }
    const nextStatus = isPaused ? "open" : "paused";
    setPausing(true);
    try {
      await mutateControlPlaneDashboardJson(`/squads/threads/${threadId}`, {
        method: "PATCH",
        body: { status: nextStatus },
        fallbackError: t("sessions.room.settings.pauseError", {
          defaultValue: "Could not change room status.",
        }),
      });
      invalidateThread();
    } catch (err) {
      showRequestError(err);
    } finally {
      setPausing(false);
    }
  }, [detail, invalidateThread, isPaused, pausing, showRequestError, showToast, status, t, threadId]);

  const displayTitle = detail?.thread.title || "";
  const photoUrl = photoPreviewUrl ?? detail?.thread.photoUrl ?? "";
  const memberCount = participants.length;

  const memberLabel = useMemo(() => {
    if (memberCount === 0) {
      return t("sessions.room.settings.zeroMembers", {
        defaultValue: "No members yet",
      });
    }
    if (memberCount === 1) {
      return t("sessions.room.settings.oneMember", {
        defaultValue: "1 member",
      });
    }
    return t("sessions.room.settings.nMembers", {
      defaultValue: "{{count}} members",
      count: memberCount,
    });
  }, [memberCount, t]);

  if (!detail && detailQuery.isPending) {
    return (
      <RoomSettingsSkeleton
        inline={inline}
        className={className}
      />
    );
  }

  return (
    <>
      <div
        className={cn(
          "flex min-h-0 flex-col",
          inline && "h-full overflow-y-auto px-4 py-4",
          className,
        )}
      >
        {/* Hero */}
        <section
          className={cn(
            "flex gap-3",
            inline
              ? "items-center border-b border-[color:var(--divider-hair)] px-0 pb-3 pt-0"
              : "flex-col items-center px-4 pb-4 pt-3",
          )}
        >
          <RoomPhotoEditor
            threadId={threadId}
            currentPhotoUrl={photoUrl}
            background={deriveAvatarColor(detail?.thread.id ?? threadId)}
            initials={deriveInitials(titleDraft || displayTitle)}
            size={inline ? "compact" : "default"}
            onUploaded={({ photoUrl: nextUrl }) => {
              setPhotoPreviewUrl(nextUrl);
              invalidateThread();
            }}
            onRemoved={() => {
              setPhotoPreviewUrl("");
              invalidateThread();
            }}
          />
          <div
            className={cn(
              "flex min-w-0 flex-col",
              inline ? "flex-1 items-start gap-0.5" : "w-full items-center gap-2",
            )}
          >
            <div
              className={cn(
                "relative min-w-0",
                inline ? "w-full" : "w-full max-w-[22rem]",
              )}
            >
              <input
                type="text"
                value={titleDraft}
                onChange={(event) => {
                  setTitleDraft(event.target.value);
                  setTitleDirty(true);
                }}
                onBlur={() => void handleSaveTitle()}
                onKeyDown={handleTitleKeyDown}
                disabled={!detail || savingMeta}
                maxLength={200}
                aria-label={t("sessions.room.settings.nameLabel", {
                  defaultValue: "Room name",
                })}
                placeholder={t("sessions.room.settings.namePlaceholder", {
                  defaultValue: "Room name",
                })}
                className={cn(
                  "h-8 w-full truncate rounded-[var(--radius-input)] border border-transparent bg-transparent px-2.5 pr-8 font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)] outline-none",
                  "transition-[border-color,background-color,box-shadow] duration-[140ms] ease-[var(--ease-out-quart)]",
                  "hover:border-[color:var(--border-subtle)] hover:bg-[var(--panel-soft)]",
                  "focus:border-[color:var(--border-strong)] focus:bg-[var(--panel-soft)] focus:shadow-[0_0_0_1px_var(--border-strong)]",
                  "disabled:cursor-wait disabled:opacity-80",
                  inline
                    ? "text-left text-[0.9375rem] leading-5"
                    : "text-center text-[1.0625rem]",
                )}
              />
              <span
                aria-hidden
                className={cn(
                  "pointer-events-none absolute top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]",
                  inline ? "right-2" : "right-3",
                )}
              >
                {savingMeta ? (
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
                ) : (
                  <PencilLine className="h-3.5 w-3.5 opacity-70" strokeWidth={1.75} />
                )}
              </span>
            </div>
            <p
              className={cn(
                "m-0 text-[var(--text-tertiary)]",
                inline ? "text-left text-[0.75rem]" : "text-center text-[0.8125rem]",
              )}
            >
              {memberLabel}
            </p>
          </div>
        </section>

        {/* Room actions */}
        <section
          className={cn(
            "gap-1.5 pb-3",
            inline
              ? "flex border-b border-[color:var(--divider-hair)] px-0 py-2.5"
              : "grid grid-cols-3 px-4",
          )}
        >
          {!inline ? (
            <ActionTile
              icon={<MessageSquare className="h-4 w-4" strokeWidth={1.75} />}
              label={t("sessions.room.settings.action.message", {
                defaultValue: "Message",
              })}
              onClick={onClose}
            />
          ) : null}
          <ActionTile
            variant={inline ? "compact" : "tile"}
            icon={
              isPaused ? (
                <Play className="h-4 w-4" strokeWidth={1.75} />
              ) : (
                <Pause className="h-4 w-4" strokeWidth={1.75} />
              )
            }
            label={
              isPaused
                ? t("sessions.room.settings.action.resume", {
                    defaultValue: "Resume",
                  })
                : t("sessions.room.settings.action.pause", {
                    defaultValue: "Pause",
                  })
            }
            busy={pausing}
            onClick={() => void handleTogglePause()}
          />
          <ActionTile
            variant={inline ? "compact" : "tile"}
            icon={<Archive className="h-4 w-4" strokeWidth={1.75} />}
            label={t("sessions.room.settings.action.archive", {
              defaultValue: "Archive",
            })}
            tone="danger"
            onClick={() => setArchiveOpen(true)}
          />
        </section>

        {/* Members card */}
        <section className={cn(inline ? "px-0 pb-0 pt-3" : "px-4 pb-4")}>
          <div
            className={cn(
              !inline &&
                "overflow-hidden rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)]",
            )}
          >
            <header
              className={cn(
                "flex items-center justify-between gap-2 pb-1.5",
                inline ? "px-0 pt-0" : "px-3 pt-2.5",
              )}
            >
              <span className="flex items-center gap-2 text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                <Users className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                {t("sessions.room.settings.members.eyebrow", {
                  defaultValue: "Members",
                })}
              </span>
              <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                {participants.length}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing((current) => !current);
                  setShowAddPicker(false);
                }}
                disabled={!detail || Boolean(pendingMutation)}
                className={cn(
                  "ml-auto h-6 px-1.5 text-[0.6875rem] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                  !inline && "h-7 px-2",
                )}
              >
                {editing
                  ? t("sessions.room.settings.done", { defaultValue: "Done" })
                  : t("sessions.room.settings.manage", {
                      defaultValue: "Manage",
                    })}
              </Button>
            </header>
            <ul className="flex flex-col">
              {participants.map((participant, index) => {
                const meta = labelFor(participant.agentId);
                const role = (participant.role || "worker") as ParticipantRole;
                const isCoordinator = role === "coordinator";
                const agentPaused =
                  statusById.get(participant.agentId) === "paused";
                return (
                  <li
                    key={participant.agentId}
                    className={cn(
                      "flex items-center gap-2.5",
                      inline ? "py-1.5" : "py-2",
                      inline ? "px-0" : "px-3",
                      index !== 0 && "border-t border-[color:var(--divider-hair)]",
                    )}
                  >
                    <AgentGlyph
                      agentId={participant.agentId}
                      color={meta.color}
                      shape="orb"
                      className={cn("shrink-0", inline ? "h-6 w-6" : "h-7 w-7")}
                    />
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span
                        className={cn(
                          "flex items-center gap-1.5 truncate font-medium text-[var(--text-primary)]",
                          inline ? "text-[0.78125rem]" : "text-[0.8125rem]",
                        )}
                      >
                        {meta.label}
                        {isCoordinator ? (
                          <Crown
                            className="h-3 w-3 text-[var(--accent)]"
                            strokeWidth={2}
                            aria-label={t(
                              "sessions.room.settings.coordinator",
                              { defaultValue: "Coordinator" },
                            )}
                          />
                        ) : null}
                        {agentPaused ? (
                          <span className="ml-1 rounded-[var(--radius-chip)] bg-[var(--tone-warning-bg)] px-1.5 py-0.5 font-mono text-[0.5625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--tone-warning-text)]">
                            {t("sessions.room.create.pausedBadge", {
                              defaultValue: "paused",
                            })}
                          </span>
                        ) : null}
                      </span>
                      <span
                        className={cn(
                          "truncate text-[var(--text-tertiary)]",
                          inline ? "text-[0.6875rem]" : "text-[0.71875rem]",
                        )}
                      >
                        {role}
                      </span>
                    </div>
                    {editing ? (
                      <>
                        <RoleSelect
                          value={role}
                          busy={pendingMutation === `role:${participant.agentId}`}
                          onChange={(next) => {
                            if (next === role) return;
                            void handleSetRole(participant.agentId, next);
                          }}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => void handleRemove(participant.agentId)}
                          disabled={
                            pendingMutation === `remove:${participant.agentId}`
                          }
                          aria-label={t("sessions.room.settings.removeAgent", {
                            defaultValue: "Remove from room",
                          })}
                          className="h-7 w-7 px-0 text-[var(--text-tertiary)] hover:bg-[var(--tone-danger-bg)] hover:text-[var(--tone-danger-dot)]"
                        >
                          <UserMinus
                            className="h-3.5 w-3.5"
                            strokeWidth={1.75}
                            aria-hidden
                          />
                        </Button>
                      </>
                    ) : null}
                  </li>
                );
              })}

              {editing && candidateAgents.length > 0 ? (
                <li className="border-t border-[color:var(--divider-hair)]">
                  {showAddPicker ? (
                    <div className="flex max-h-[220px] flex-col gap-1 overflow-y-auto p-1">
                      {candidateAgents.map((agent) => {
                        const isPaused =
                          statusById.get(agent.id) === "paused";
                        return (
                          <button
                            key={agent.id}
                            type="button"
                            onClick={() => void handleAdd(agent.id)}
                            disabled={pendingMutation === `add:${agent.id}`}
                            className="flex w-full items-center gap-2.5 rounded-[var(--radius-panel-sm)] p-2 text-left transition-colors hover:bg-[var(--hover-tint)] disabled:opacity-60"
                          >
                            <AgentGlyph
                              agentId={agent.id}
                              color={agent.color}
                              shape="orb"
                              className="h-6 w-6 shrink-0"
                            />
                            <div className="flex min-w-0 flex-1 flex-col">
                              <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                                {agent.label || agent.id}
                              </span>
                              {agent.label && agent.label !== agent.id ? (
                                <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                                  {agent.id}
                                </span>
                              ) : null}
                            </div>
                            {isPaused ? (
                              <span className="rounded-[var(--radius-chip)] bg-[var(--tone-warning-bg)] px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--tone-warning-text)]">
                                {t("sessions.room.create.pausedBadge", {
                                  defaultValue: "paused",
                                })}
                              </span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className={cn("py-2", inline ? "px-0" : "px-3")}>
                      <button
                        type="button"
                        onClick={() => setShowAddPicker(true)}
                        className={cn(
                          "inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-pill)] border border-[color:var(--border-subtle)] bg-transparent px-2.5",
                          "text-[0.75rem] font-medium tracking-[-0.005em] text-[var(--text-secondary)]",
                          "transition-[background-color,border-color,color] duration-[120ms] ease-[var(--ease-out-quart)]",
                          "hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                          "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]",
                        )}
                      >
                        <Plus className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                        {t("sessions.room.settings.addMember", {
                          defaultValue: "Add member",
                        })}
                      </button>
                    </div>
                  )}
                </li>
              ) : null}
            </ul>
          </div>
        </section>
      </div>

      <ConfirmationDialog
        open={archiveOpen}
        title={t("sessions.room.settings.confirmArchiveTitle", {
          defaultValue: "Archive this room?",
        })}
        message={t("sessions.room.settings.confirmArchiveMessage", {
          defaultValue:
            "The room will disappear from your rail. Conversation history is preserved on the backend and can be restored.",
        })}
        confirmLabel={
          archivingPending
            ? t("sessions.room.settings.archiving", {
                defaultValue: "Archiving…",
              })
            : t("sessions.room.settings.confirmArchive", {
                defaultValue: "Archive",
              })
        }
        onConfirm={() => void handleArchive()}
        onCancel={() => {
          if (archivingPending) return;
          setArchiveOpen(false);
        }}
      />
    </>
  );
}

function RoomSettingsSkeleton({
  inline,
  className,
}: {
  inline: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-0 flex-col",
        inline && "h-full overflow-y-auto px-4 py-4",
        className,
      )}
    >
      <section
        aria-label="Loading room settings"
        className={cn(
          "flex gap-3 border-b border-[color:var(--divider-hair)] px-0 pb-3 pt-0",
          inline ? "items-center" : "flex-col items-center px-4 pt-3",
        )}
      >
        <div
          className={cn(
            "animate-pulse rounded-full bg-[var(--panel-strong)]",
            inline ? "h-14 w-14" : "h-20 w-20",
          )}
        />
        <div
          className={cn(
            "flex min-w-0 flex-col gap-2",
            inline ? "flex-1" : "w-full max-w-[22rem] items-center",
          )}
        >
          <div
            className={cn(
              "h-6 animate-pulse rounded-[var(--radius-input)] bg-[var(--panel-strong)]",
              inline ? "w-4/5" : "w-2/3",
            )}
          />
          <div
            className={cn(
              "h-3 animate-pulse rounded-full bg-[var(--panel-soft)]",
              inline ? "w-24" : "w-20",
            )}
          />
        </div>
      </section>
      <section className="border-b border-[color:var(--divider-hair)] py-2.5">
        <div className="grid grid-cols-2 gap-1.5">
          <div className="h-8 animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]" />
          <div className="h-8 animate-pulse rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)]" />
        </div>
      </section>
      <section className="space-y-3 py-3">
        <div className="h-3 w-20 animate-pulse rounded-full bg-[var(--panel-strong)]" />
        <div className="h-4 w-full animate-pulse rounded-full bg-[var(--panel-soft)]" />
      </section>
    </div>
  );
}

function ActionTile({
  icon,
  label,
  onClick,
  busy = false,
  disabled = false,
  tone = "primary",
  variant = "tile",
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  busy?: boolean;
  disabled?: boolean;
  tone?: "primary" | "danger";
  variant?: "tile" | "compact";
}) {
  const compact = variant === "compact";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className={cn(
        "transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]",
        compact
          ? "inline-flex h-8 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-transparent bg-transparent px-2 text-[0.75rem] font-medium"
          : "group flex min-h-[72px] flex-col items-center justify-center gap-1 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-2 py-2.5 text-[0.75rem] font-medium hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)]",
        compact && tone === "danger"
          ? "text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg)] hover:text-[var(--tone-danger-dot)]"
          : null,
        compact && tone !== "danger"
          ? "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
          : null,
        !compact && tone === "danger"
          ? "text-[var(--tone-danger-dot)] hover:border-[color:var(--tone-danger-border)]"
          : null,
        !compact && tone !== "danger" ? "text-[var(--text-primary)]" : null,
        compact
          ? "disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
          : "disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-[color:var(--border-subtle)] disabled:hover:bg-[var(--panel-soft)]",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "transition-[background-color,color] duration-[120ms]",
          compact
            ? "inline-flex h-4 w-4 items-center justify-center"
            : "inline-flex h-7 w-7 items-center justify-center rounded-full",
          compact && tone === "danger" ? "text-current" : null,
          compact && tone !== "danger" ? "text-current" : null,
          !compact && tone === "danger"
            ? "bg-[var(--tone-danger-bg)] text-[var(--tone-danger-dot)]"
            : null,
          !compact && tone !== "danger"
            ? "bg-[var(--panel-strong)] text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]"
            : null,
        )}
      >
        {busy ? (
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} aria-hidden />
        ) : (
          icon
        )}
      </span>
      <span className="truncate tracking-[-0.005em]">{label}</span>
    </button>
  );
}

const ROLE_META: Record<
  ParticipantRole,
  {
    icon: React.ComponentType<{ className?: string; strokeWidth?: number; "aria-hidden"?: boolean }>;
    labelKey: string;
    fallbackLabel: string;
    descriptionKey: string;
    fallbackDescription: string;
  }
> = {
  coordinator: {
    icon: Crown,
    labelKey: "sessions.room.settings.role.coordinator",
    fallbackLabel: "Coordinator",
    descriptionKey: "sessions.room.settings.role.coordinatorHint",
    fallbackDescription: "Drives the room and routes work.",
  },
  worker: {
    icon: UserRound,
    labelKey: "sessions.room.settings.role.worker",
    fallbackLabel: "Worker",
    descriptionKey: "sessions.room.settings.role.workerHint",
    fallbackDescription: "Picks up tasks and replies.",
  },
  observer: {
    icon: Eye,
    labelKey: "sessions.room.settings.role.observer",
    fallbackLabel: "Observer",
    descriptionKey: "sessions.room.settings.role.observerHint",
    fallbackDescription: "Reads only — no auto-replies.",
  },
};

function RoleSelect({
  value,
  busy,
  onChange,
}: {
  value: ParticipantRole;
  busy: boolean;
  onChange: (next: ParticipantRole) => void;
}) {
  const { t } = useAppI18n();
  const [open, setOpen] = useState(false);
  const meta = ROLE_META[value];
  const Icon = meta.icon;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={busy}
          aria-label={t("sessions.room.settings.role", {
            defaultValue: "Role",
          })}
          data-state={open ? "open" : "closed"}
          className={cn(
            "inline-flex h-7 shrink-0 items-center gap-1 rounded-[var(--radius-pill)] px-2.5",
            "border border-[color:var(--border-subtle)] bg-[var(--panel-soft)]",
            "text-[0.6875rem] font-medium tracking-[-0.005em] text-[var(--text-secondary)]",
            "transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
            "data-[state=open]:border-[color:var(--border-strong)] data-[state=open]:bg-[var(--surface-hover)] data-[state=open]:text-[var(--text-primary)]",
            "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]",
            "disabled:opacity-60",
          )}
        >
          <Icon className="h-3 w-3" strokeWidth={2} aria-hidden />
          <span>{t(meta.labelKey, { defaultValue: meta.fallbackLabel })}</span>
          <ChevronDown
            className={cn(
              "h-2.5 w-2.5 text-[var(--text-tertiary)] transition-transform duration-[120ms]",
              open && "rotate-180",
            )}
            strokeWidth={2}
            aria-hidden
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={6}
        className="w-[200px] p-1"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <ul role="listbox" className="flex flex-col">
          {ROLE_OPTIONS.map((role) => {
            const optionMeta = ROLE_META[role];
            const OptionIcon = optionMeta.icon;
            const selected = role === value;
            return (
              <li key={role}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    setOpen(false);
                    if (role !== value) onChange(role);
                  }}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-[var(--radius-panel-sm)] px-2 py-2 text-left",
                    "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                    "hover:bg-[var(--hover-tint)]",
                    selected
                      ? "text-[var(--text-primary)]"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                      selected
                        ? "bg-[var(--accent)] text-[var(--accent-text)]"
                        : "bg-[var(--panel-strong)] text-[var(--text-tertiary)]",
                    )}
                  >
                    <OptionIcon className="h-3 w-3" strokeWidth={2} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-[0.8125rem] font-medium">
                      {t(optionMeta.labelKey, {
                        defaultValue: optionMeta.fallbackLabel,
                      })}
                    </span>
                    <span className="text-[0.6875rem] text-[var(--text-tertiary)] leading-[1.35]">
                      {t(optionMeta.descriptionKey, {
                        defaultValue: optionMeta.fallbackDescription,
                      })}
                    </span>
                  </span>
                  {selected ? (
                    <Check
                      className="mt-0.5 h-3 w-3 shrink-0 text-[var(--accent)]"
                      strokeWidth={2.5}
                      aria-hidden
                    />
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
