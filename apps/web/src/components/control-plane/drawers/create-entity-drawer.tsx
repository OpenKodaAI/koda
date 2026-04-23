"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import {
  SELECT_ALL_VALUE,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";
import { cn } from "@/lib/utils";

export type CreateEntityType = "workspace" | "squad" | "agent";

interface WorkspaceLike {
  id: string;
  name: string;
  squads: Array<{ id: string; name: string }>;
}

interface AgentLike {
  id: string;
}

interface CreateEntityDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultType?: CreateEntityType;
  defaultWorkspaceId?: string | null;
  defaultSquadId?: string | null;
  workspaces?: WorkspaceLike[];
  agents?: AgentLike[];
  onCreated?: () => void;
}

const PRESET_COLORS = [
  "#D97757",
  "#6E97D9",
  "#7FA877",
  "#BC8BD7",
  "#D9A85B",
  "#5BAABB",
  "#C97F9A",
  "#8B90AD",
];

function slugifyId(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function hexToRgb(hex: string): string {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return "122, 135, 153";
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `${r}, ${g}, ${b}`;
}

function suggestHealthPort(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) % 10000;
  }
  return 8100 + (hash % 800);
}

export function CreateEntityDrawer({
  open,
  onOpenChange,
  defaultType = "workspace",
  defaultWorkspaceId = null,
  defaultSquadId = null,
  workspaces = [],
  agents = [],
  onCreated,
}: CreateEntityDrawerProps) {
  const { t } = useAppI18n();
  const router = useRouter();

  const [type, setType] = useState<CreateEntityType>(defaultType);
  const [name, setName] = useState("");
  const [agentIdDraft, setAgentIdDraft] = useState("");
  const [agentIdTouched, setAgentIdTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [color, setColor] = useState<string>(PRESET_COLORS[0]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(defaultWorkspaceId);
  const [squadId, setSquadId] = useState<string | null>(defaultSquadId);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setType(defaultType);
    setWorkspaceId(defaultWorkspaceId);
    setSquadId(defaultSquadId);
    setName("");
    setAgentIdDraft("");
    setAgentIdTouched(false);
    setDescription("");
    setColor(PRESET_COLORS[0]);
    setSubmitting(false);
    setError(null);
  }, [open, defaultType, defaultWorkspaceId, defaultSquadId]);

  const derivedAgentId = useMemo(() => {
    if (agentIdTouched && agentIdDraft) return slugifyId(agentIdDraft);
    return slugifyId(name);
  }, [agentIdDraft, agentIdTouched, name]);

  const availableSquads = useMemo(() => {
    if (!workspaceId) return [] as { id: string; name: string }[];
    const workspace = workspaces.find((item) => item.id === workspaceId);
    return workspace?.squads ?? [];
  }, [workspaceId, workspaces]);

  useEffect(() => {
    if (!workspaceId) {
      setSquadId(null);
      return;
    }
    if (!availableSquads.some((squad) => squad.id === squadId)) {
      setSquadId(null);
    }
  }, [workspaceId, availableSquads, squadId]);

  const title = t(`controlPlane.create.title.${type}`, {
    defaultValue:
      type === "workspace"
        ? "New workspace"
        : type === "squad"
          ? "New squad"
          : "New agent",
  });

  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (!name.trim()) return false;
    if (type === "squad" && !workspaceId) return false;
    if (type === "agent" && !derivedAgentId) return false;
    if (type === "agent" && agents.some((agent) => agent.id === derivedAgentId)) return false;
    return true;
  }, [submitting, name, type, workspaceId, derivedAgentId, agents]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      if (type === "workspace") {
        await requestJson<unknown>("/api/control-plane/workspaces", {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            description: description.trim(),
          }),
        });
      } else if (type === "squad") {
        if (!workspaceId) throw new Error("Workspace is required");
        await requestJson<unknown>(
          `/api/control-plane/workspaces/${workspaceId}/squads`,
          {
            method: "POST",
            body: JSON.stringify({
              name: name.trim(),
              description: description.trim(),
            }),
          },
        );
      } else {
        const agentId = derivedAgentId;
        const healthPort = suggestHealthPort(agentId);
        await requestJson<unknown>("/api/control-plane/agents", {
          method: "POST",
          body: JSON.stringify({
            id: agentId,
            display_name: name.trim() || agentId.replace(/_/g, " "),
            status: "paused",
            storage_namespace: agentId.toLowerCase(),
            appearance: {
              label: name.trim() || agentId,
              color,
              color_rgb: hexToRgb(color),
            },
            runtime_endpoint: {
              health_port: healthPort,
              health_url: `http://127.0.0.1:${healthPort}/health`,
              runtime_base_url: `http://127.0.0.1:${healthPort}`,
            },
            organization: {
              workspace_id: workspaceId,
              squad_id: workspaceId ? squadId : null,
            },
          }),
        });
      }

      router.refresh();
      onCreated?.();
      onOpenChange(false);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : t("controlPlane.create.genericError", {
              defaultValue: "Could not save. Please try again.",
            }),
      );
    } finally {
      setSubmitting(false);
    }
  }

  const namePlaceholder =
    type === "workspace"
      ? t("controlPlane.create.name.workspace", { defaultValue: "Acme Product" })
      : type === "squad"
        ? t("controlPlane.create.name.squad", { defaultValue: "Platform" })
        : t("controlPlane.create.name.agent", { defaultValue: "Pixie" });

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={t("controlPlane.create.subtitle", {
        defaultValue: "Choose what you want to add and fill in the basics.",
      })}
      width="min(460px, 96vw)"
    >
      <form onSubmit={handleSubmit} className="flex h-full flex-col">
        <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-6 py-6">
          <fieldset className="flex flex-col gap-2">
            <legend className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("controlPlane.create.typeLabel", { defaultValue: "Type" })}
            </legend>
            <div
              role="radiogroup"
              aria-label={t("controlPlane.create.typeLabel", { defaultValue: "Type" })}
              className="grid grid-cols-3 gap-1 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-1"
            >
              {(["workspace", "squad", "agent"] as const).map((option) => {
                const active = type === option;
                return (
                  <button
                    key={option}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setType(option)}
                    className={cn(
                      "inline-flex h-10 items-center justify-center rounded-[var(--radius-pill)] text-[0.8125rem] font-medium",
                      "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                      active
                        ? "bg-[var(--panel)] text-[var(--text-primary)]"
                        : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                    )}
                  >
                    {t(`controlPlane.create.type.${option}`, {
                      defaultValue:
                        option === "workspace"
                          ? "Workspace"
                          : option === "squad"
                            ? "Squad"
                            : "Agent",
                    })}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <label className="flex flex-col gap-2">
            <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("controlPlane.create.nameLabel", { defaultValue: "Name" })}
            </span>
            <Input
              sizeVariant="md"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={namePlaceholder}
              autoFocus
              disabled={submitting}
            />
          </label>

          {type === "agent" ? (
            <label className="flex flex-col gap-2">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("controlPlane.create.agentIdLabel", { defaultValue: "Agent ID" })}
              </span>
              <Input
                sizeVariant="md"
                value={agentIdTouched ? agentIdDraft : derivedAgentId}
                onChange={(event) => {
                  setAgentIdTouched(true);
                  setAgentIdDraft(event.target.value.toUpperCase());
                }}
                placeholder={t("controlPlane.create.agentIdPlaceholder", {
                  defaultValue: "PIXIE",
                })}
                disabled={submitting}
              />
              <span className="text-[0.75rem] text-[var(--text-quaternary)]">
                {t("controlPlane.create.agentIdHint", {
                  defaultValue: "Uppercase letters, numbers and underscores only.",
                })}
              </span>
            </label>
          ) : null}

          <label className="flex flex-col gap-2">
            <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("controlPlane.create.descriptionLabel", { defaultValue: "Description" })}
            </span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t("controlPlane.create.descriptionPlaceholder", {
                defaultValue: "Short summary (optional)",
              })}
              disabled={submitting}
              rows={3}
              className="min-h-[96px] w-full resize-none rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3.5 py-2.5 text-[0.875rem] leading-[1.5] text-[var(--text-primary)] outline-none transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] placeholder:text-[var(--text-quaternary)] focus-visible:border-[var(--accent)] focus-visible:bg-[var(--panel)]"
            />
          </label>

          {type === "agent" ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("controlPlane.create.colorLabel", { defaultValue: "Color" })}
              </legend>
              <div className="flex flex-wrap items-center gap-2.5">
                {PRESET_COLORS.map((option) => {
                  const active = option === color;
                  return (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setColor(option)}
                      aria-label={option}
                      aria-pressed={active}
                      className={cn(
                        "relative h-9 w-9 rounded-full border-2 transition-all duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                        active
                          ? "border-[var(--text-primary)]"
                          : "border-transparent hover:border-[var(--text-tertiary)]",
                      )}
                      style={{ background: option }}
                    />
                  );
                })}
              </div>
            </fieldset>
          ) : null}

          {type === "squad" || type === "agent" ? (
            <label className="flex flex-col gap-2">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {type === "squad"
                  ? t("controlPlane.create.parentWorkspace", {
                      defaultValue: "Parent workspace",
                    })
                  : t("controlPlane.create.workspaceOptional", {
                      defaultValue: "Workspace (optional)",
                    })}
              </span>
              <Select
                value={workspaceId ?? SELECT_ALL_VALUE}
                onValueChange={(v) => setWorkspaceId(v === SELECT_ALL_VALUE ? null : v)}
                disabled={submitting || workspaces.length === 0}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_ALL_VALUE}>
                    {type === "agent"
                      ? t("controlPlane.create.workspaceNone", {
                          defaultValue: "No workspace (unassigned)",
                        })
                      : t("controlPlane.create.workspaceChoose", {
                          defaultValue: "Choose a workspace",
                        })}
                  </SelectItem>
                  {workspaces.map((workspace) => (
                    <SelectItem key={workspace.id} value={workspace.id}>
                      {workspace.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          ) : null}

          {type === "agent" && workspaceId ? (
            <label className="flex flex-col gap-2">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("controlPlane.create.squadOptional", {
                  defaultValue: "Squad (optional)",
                })}
              </span>
              <Select
                value={squadId ?? SELECT_ALL_VALUE}
                onValueChange={(v) => setSquadId(v === SELECT_ALL_VALUE ? null : v)}
                disabled={submitting || availableSquads.length === 0}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SELECT_ALL_VALUE}>
                    {t("controlPlane.create.squadNone", {
                      defaultValue: "No squad",
                    })}
                  </SelectItem>
                  {availableSquads.map((squad) => (
                    <SelectItem key={squad.id} value={squad.id}>
                      {squad.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          ) : null}

          {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-[var(--divider-hair)] px-6 py-4">
          <Button
            variant="ghost"
            size="md"
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            {t("controlPlane.create.cancel", { defaultValue: "Cancel" })}
          </Button>
          <Button variant="accent" size="md" type="submit" disabled={!canSubmit}>
            {submitting ? (
              <Loader2 className="icon-sm animate-spin" strokeWidth={1.75} aria-hidden />
            ) : null}
            {t("controlPlane.create.submit", { defaultValue: "Create" })}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}

export type { WorkspaceLike, AgentLike };
