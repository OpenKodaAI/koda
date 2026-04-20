"use client";

import {
  type DragEvent,
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { CheckCheck, ChevronDown, FileText, FolderPlus, LoaderCircle, Pencil, Plus, Trash2, Users } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { AgentCatalogCard } from "./agent-catalog-card";
import { WorkspaceSpecEditor, WorkspaceSpecIndicator } from "./workspace-spec-editor";
import { SquadSpecEditor, SquadSpecIndicator } from "./squad-spec-editor";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { FormInput } from "@/components/control-plane/shared/form-field";
import {
  PageMetricStrip,
  PageMetricStripItem,
  PageSearchField,
} from "@/components/ui/page-primitives";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useCreateAgent } from "@/hooks/use-create-agent";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import type {
  ControlPlaneAgentSummary,
  ControlPlaneAgentOrganization,
  ControlPlaneWorkspace,
  ControlPlaneWorkspaceSquad,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

const NO_WORKSPACE_KEY = "__no_workspace__";
const NO_SQUAD_KEY = "__no_squad__";
const MIN_WORKSPACE_LANES = 3;

/* ------------------------------------------------------------------ */
/*  WorkspaceSelectorDropdown                                         */
/* ------------------------------------------------------------------ */

function WorkspaceSelectorDropdown({
  workspaceTabs,
  activeSection,
  onSelect,
  tl,
}: {
  workspaceTabs: BoardSection[];
  activeSection: BoardSection | null;
  onSelect: (key: string) => void;
  tl: (value: string, options?: Record<string, unknown>) => string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      const pad = 12;
      const w = Math.max(220, rect.width);
      const left = Math.min(
        Math.max(rect.left, pad),
        window.innerWidth - pad - w,
      );
      setPanelPosition({ top: rect.bottom + 6, left, width: w });
    };

    const frame = requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className="flex h-8 w-full min-w-[180px] max-w-[240px] items-center justify-between gap-2.5 rounded-[calc(var(--radius-input)-4px)] bg-transparent px-2 text-left transition-colors duration-[var(--transition-fast)] hover:bg-[var(--hover-tint)]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={tl("Selecionar workspace")}
      >
        <span className="flex min-w-0 items-center gap-2.5">
          {activeSection && (
            <span
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--panel-soft)] text-[10px] font-medium tabular-nums text-[var(--text-tertiary)]"
              aria-hidden="true"
              title={tl("{{count}} agents", { count: activeSection.totalAgents })}
            >
              {activeSection.totalAgents}
            </span>
          )}
          <span className="block min-w-0 truncate text-sm font-medium text-[var(--text-primary)]">
            {activeSection?.title ?? tl("Workspace")}
          </span>
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-[var(--text-quaternary)] transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      {typeof document !== "undefined"
        ? createPortal(
            <AnimatePresence initial={false}>
              {open ? (
                <motion.div
                  ref={panelRef}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
                  className="app-floating-panel agent-board-ws-selector__menu"
                  role="listbox"
                  aria-label={tl("Workspaces")}
                  style={{
                    position: "fixed",
                    zIndex: 80,
                    top: panelPosition?.top ?? 0,
                    left: panelPosition?.left ?? 0,
                    width: panelPosition?.width,
                    visibility: panelPosition ? "visible" : "hidden",
                  }}
                >
                  {workspaceTabs.map((section) => {
                    const isActive = section.key === activeSection?.key;

                    return (
                      <button
                        key={section.key}
                        type="button"
                        role="option"
                        aria-selected={isActive}
                        className={cn(
                          "agent-board-ws-selector__item",
                          isActive && "agent-board-ws-selector__item--active",
                        )}
                        onClick={() => {
                          onSelect(section.key);
                          setOpen(false);
                        }}
                      >
                        <span
                          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--panel-soft)] text-[10px] font-medium tabular-nums text-[var(--text-tertiary)]"
                          aria-hidden="true"
                          title={tl("{{count}} agents", { count: section.totalAgents })}
                        >
                          {section.totalAgents}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{section.title}</span>
                      </button>
                    );
                  })}
                </motion.div>
              ) : null}
            </AnimatePresence>,
            document.body,
          )
        : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CreatePopover                                                     */
/* ------------------------------------------------------------------ */

function CreatePopover({
  onCreateAgent,
  onCreateWorkspace,
  onCreateSquad,
  hasActiveWorkspace,
  tl,
}: {
  onCreateAgent: () => void;
  onCreateWorkspace: () => void;
  onCreateSquad: () => void;
  hasActiveWorkspace: boolean;
  tl: (value: string, options?: Record<string, unknown>) => string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      const pad = 12;
      const w = 208;
      const left = Math.min(
        Math.max(rect.right - w, pad),
        window.innerWidth - pad - w,
      );
      setPanelPosition({ top: rect.bottom + 6, left, width: w });
    };

    const frame = requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={cn(
          "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[calc(var(--radius-input)-4px)] bg-[var(--panel-strong)] text-[var(--text-primary)] transition-colors duration-[var(--transition-fast)] hover:bg-[var(--surface-hover)] active:scale-[0.96] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
          open && "bg-[var(--surface-hover)]",
        )}
        aria-label={tl("Criar")}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        <Plus className="icon-sm" strokeWidth={1.75} />
      </button>

      {typeof document !== "undefined"
        ? createPortal(
            <AnimatePresence initial={false}>
              {open ? (
                <motion.div
                  ref={panelRef}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
                  className="app-floating-panel agent-board-create-popover__menu"
                  role="menu"
                  aria-label={tl("Criar")}
                  style={{
                    position: "fixed",
                    zIndex: 80,
                    top: panelPosition?.top ?? 0,
                    left: panelPosition?.left ?? 0,
                    width: panelPosition?.width,
                    visibility: panelPosition ? "visible" : "hidden",
                  }}
                >
                  <button
                    type="button"
                    role="menuitem"
                    className="agent-board-create-popover__item"
                    onClick={() => {
                      onCreateAgent();
                      setOpen(false);
                    }}
                  >
                    <Plus className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" />
                    <span>{tl("Agente")}</span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="agent-board-create-popover__item"
                    onClick={() => {
                      onCreateWorkspace();
                      setOpen(false);
                    }}
                  >
                    <FolderPlus className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" />
                    <span>{tl("Workspace")}</span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="agent-board-create-popover__item"
                    disabled={!hasActiveWorkspace}
                    onClick={() => {
                      if (hasActiveWorkspace) {
                        onCreateSquad();
                        setOpen(false);
                      }
                    }}
                  >
                    <Users className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" />
                    <span>{tl("Squad")}</span>
                  </button>
                </motion.div>
              ) : null}
            </AnimatePresence>,
            document.body,
          )
        : null}
    </div>
  );
}

type OrganizationFormState = {
  kind: "workspace" | "squad";
  mode: "create" | "edit";
  targetId?: string;
  workspaceId?: string;
  workspaceName?: string;
  name: string;
  description: string;
};

type DeleteTarget =
  | { kind: "workspace"; id: string; name: string }
  | { kind: "squad"; id: string; name: string; workspaceId: string }
  | { kind: "agent"; id: string; name: string };

type BoardLane = {
  key: string;
  title: string;
  description: string;
  workspaceId: string | null;
  squadId: string | null;
  color?: string;
  totalAgents: number;
  agents: ControlPlaneAgentSummary[];
  squad: ControlPlaneWorkspaceSquad | null;
  isPlaceholder?: boolean;
};

type BoardSection = {
  key: string;
  title: string;
  description: string;
  color?: string;
  totalAgents: number;
  visibleAgents: number;
  workspace: ControlPlaneWorkspace | null;
  lanes: BoardLane[];
  isVirtual: boolean;
};

type LaneRailPanState = {
  sectionKey: string;
  startX: number;
  initialScrollLeft: number;
};

type OrganizationTarget = {
  workspace_id: string | null;
  squad_id: string | null;
};

type BatchMoveFeedback = {
  phase: "moving" | "done";
  total: number;
  completed: number;
  failed: number;
  targetLabel: string;
};

function sameOrganization(
  current: ControlPlaneAgentOrganization | OrganizationTarget | null | undefined,
  next: OrganizationTarget,
): boolean {
  const currentWorkspaceId = current?.workspace_id ?? null;
  const currentSquadId = currentWorkspaceId
    ? (current?.squad_id ?? null)
    : null;

  return (
    currentWorkspaceId === next.workspace_id &&
    currentSquadId === next.squad_id
  );
}

function buildOrganizationPreview(
  tree: ControlPlaneWorkspaceTree,
  next: OrganizationTarget,
): ControlPlaneAgentOrganization {
  if (!next.workspace_id) {
    return {
      workspace_id: null,
      workspace_name: null,
      squad_id: null,
      squad_name: null,
    };
  }

  const workspace =
    tree.items.find((item) => item.id === next.workspace_id) ?? null;
  const squad =
    workspace && next.squad_id
      ? workspace.squads.find((item) => item.id === next.squad_id) ?? null
      : null;

  return {
    workspace_id: next.workspace_id,
    workspace_name: workspace?.name ?? null,
    squad_id: next.squad_id ?? null,
    squad_name: squad?.name ?? null,
  };
}

function cloneWorkspaceTree(
  tree: ControlPlaneWorkspaceTree,
): ControlPlaneWorkspaceTree {
  return {
    ...tree,
    virtual_buckets: {
      no_workspace: { ...tree.virtual_buckets.no_workspace },
    },
    items: tree.items.map((workspace) => ({
      ...workspace,
      virtual_buckets: {
        no_squad: { ...workspace.virtual_buckets.no_squad },
      },
      squads: workspace.squads.map((squad) => ({ ...squad })),
    })),
  };
}

function applyCountDelta(
  tree: ControlPlaneWorkspaceTree,
  organization: OrganizationTarget,
  delta: number,
) {
  if (!organization.workspace_id) {
    tree.virtual_buckets.no_workspace.bot_count += delta;
    return;
  }

  const workspace = tree.items.find(
    (item) => item.id === organization.workspace_id,
  );

  if (!workspace) {
    return;
  }

  workspace.bot_count += delta;

  if (organization.squad_id) {
    const squad = workspace.squads.find(
      (item) => item.id === organization.squad_id,
    );
    if (squad) {
      squad.bot_count += delta;
    }
    return;
  }

  workspace.virtual_buckets.no_squad.bot_count += delta;
}

function applyBatchMoveToWorkspaceTree(
  tree: ControlPlaneWorkspaceTree,
  moves: Array<{ from: OrganizationTarget; to: OrganizationTarget }>,
): ControlPlaneWorkspaceTree {
  const nextTree = cloneWorkspaceTree(tree);

  for (const move of moves) {
    applyCountDelta(nextTree, move.from, -1);
    applyCountDelta(nextTree, move.to, 1);
  }

  return nextTree;
}

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

function laneKey(workspaceId: string | null, squadId: string | null): string {
  return `${workspaceId ?? NO_WORKSPACE_KEY}:${squadId ?? NO_SQUAD_KEY}`;
}

function normalizeSearchValue(value: string): string {
  return value.toLowerCase().trim();
}

function matchesAgentSearch(agent: ControlPlaneAgentSummary, query: string): boolean {
  if (!query) return true;
  const haystack = [
    agent.display_name,
    agent.id,
    agent.organization?.workspace_name,
    agent.organization?.squad_name,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function matchesWorkspaceSearch(
  workspace: ControlPlaneWorkspace,
  query: string,
): boolean {
  if (!query) return true;
  return `${workspace.name} ${workspace.description}`
    .toLowerCase()
    .includes(query);
}

function matchesSquadSearch(
  squad: ControlPlaneWorkspaceSquad | null,
  query: string,
): boolean {
  if (!query) return true;
  if (!squad) {
    return "squad".includes(query);
  }
  return `${squad.name} ${squad.description}`.toLowerCase().includes(query);
}

function canStartLaneRailPan(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) {
    return false;
  }
  return !target.closest(
    "button, a, input, textarea, select, summary, [role='button'], [draggable='true'], [data-no-lane-pan='true']",
  );
}

interface AgentCatalogProps {
  agents: ControlPlaneAgentSummary[];
  workspaces: ControlPlaneWorkspaceTree;
}

export function AgentCatalog({
  agents,
  workspaces,
}: AgentCatalogProps) {
  const router = useRouter();
  const { showToast } = useToast();
  const { tl } = useAppI18n();

  const { createAgent: createAgentViaHook } = useCreateAgent();

  const [search, setSearch] = useState("");
  const [duplicatingBotId, setDuplicatingBotId] = useState<string | null>(null);
  const [organizationForm, setOrganizationForm] =
    useState<OrganizationFormState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [organizationBusy, setOrganizationBusy] = useState(false);
  const [catalogAgents, setCatalogAgents] = useState(agents);
  const [workspaceTree, setWorkspaceTree] = useState(workspaces);
  const [activeSectionKey, setActiveSectionKey] = useState<string | null>(null);
  const [movingBotIds, setMovingBotIds] = useState<string[]>([]);
  const [draggingBotIds, setDraggingBotIds] = useState<string[]>([]);
  const [dropTargetKey, setDropTargetKey] = useState<string | null>(null);
  const [moveFeedback, setMoveFeedback] = useState<BatchMoveFeedback | null>(
    null,
  );
  const [workspaceSpecTarget, setWorkspaceSpecTarget] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [squadSpecTarget, setSquadSpecTarget] = useState<{
    workspaceId: string;
    squadId: string;
    squadName: string;
  } | null>(null);
  const laneRailRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const laneRailPanRef = useRef<LaneRailPanState | null>(null);
  const [laneRailDraggingKey, setLaneRailDraggingKey] = useState<string | null>(
    null,
  );
  const moveFeedbackTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setCatalogAgents(agents);
  }, [agents]);

  useEffect(() => {
    setWorkspaceTree(workspaces);
  }, [workspaces]);

  useEffect(() => {
    return () => {
      if (moveFeedbackTimerRef.current) {
        window.clearTimeout(moveFeedbackTimerRef.current);
      }
    };
  }, []);

  function normalizeCloneBase(base: string): string {
    const raw = base.toUpperCase().replace(/[^A-Z0-9]/g, "_");
    return raw.length === 0 ? "BOT" : raw.slice(0, 20);
  }

  function generateDuplicateBotId(baseId: string): string {
    const base = `${normalizeCloneBase(baseId)}_COPY`;
    const usedIds = new Set(catalogAgents.map((item) => item.id));
    if (!usedIds.has(base)) {
      return base;
    }

    for (let suffix = 2; ; suffix += 1) {
      const candidate = `${base}_${suffix}`;
      if (!usedIds.has(candidate)) {
        return candidate;
      }
    }
  }

  useEffect(() => {
    if (!laneRailDraggingKey) {
      return;
    }

    const handleMouseMove = (event: MouseEvent) => {
      const panState = laneRailPanRef.current;
      if (!panState) {
        return;
      }
      const rail = laneRailRefs.current[panState.sectionKey];
      if (!rail) {
        return;
      }
      const deltaX = event.clientX - panState.startX;
      rail.scrollLeft = panState.initialScrollLeft - deltaX;
    };

    const handleMouseUp = () => {
      laneRailPanRef.current = null;
      setLaneRailDraggingKey(null);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [laneRailDraggingKey]);

  const metrics = useMemo(() => {
    const active = catalogAgents.filter((agent) => agent.status === "active").length;
    const paused = catalogAgents.filter((agent) => agent.status === "paused").length;
    const squadCount = workspaceTree.items.reduce(
      (total, workspace) => total + workspace.squads.length,
      0,
    );
    return {
      totalAgents: catalogAgents.length,
      active,
      paused,
      workspaces: workspaceTree.items.length,
      squads: squadCount,
    };
  }, [catalogAgents, workspaceTree.items]);

  const searchQuery = normalizeSearchValue(search);

  const filteredAgents = useMemo(
    () => catalogAgents.filter((agent) => matchesAgentSearch(agent, searchQuery)),
    [catalogAgents, searchQuery],
  );

  const movingAgentIdSet = useMemo(
    () => new Set(movingBotIds),
    [movingBotIds],
  );

  const boardSections = useMemo(() => {
    const filteredByLane = new Map<string, ControlPlaneAgentSummary[]>();

    for (const agent of filteredAgents) {
      const key = laneKey(
        agent.organization?.workspace_id ?? null,
        agent.organization?.workspace_id
          ? (agent.organization?.squad_id ?? null)
          : null,
      );
      const items = filteredByLane.get(key) ?? [];
      items.push(agent);
      filteredByLane.set(key, items);
    }

    const sections: BoardSection[] = [];
    const noWorkspaceAgents = filteredByLane.get(laneKey(null, null)) ?? [];
    const includeNoWorkspace =
      !searchQuery ||
      noWorkspaceAgents.length > 0 ||
      tl("Sem workspace").toLowerCase().includes(searchQuery);

    if (includeNoWorkspace) {
      sections.push({
        key: NO_WORKSPACE_KEY,
        title: tl("Sem workspace"),
        description:
          tl("Bots livres, ainda fora de um workspace. Arraste para organizar."),
        color: "#707A8C",
        totalAgents: workspaceTree.virtual_buckets.no_workspace.bot_count,
        visibleAgents: noWorkspaceAgents.length,
        workspace: null,
        isVirtual: true,
        lanes: [
          {
            key: laneKey(null, null),
            title: tl("Bots livres"),
            description:
              tl("Solte aqui para remover o vínculo com qualquer workspace."),
            workspaceId: null,
            squadId: null,
            color: "#707A8C",
            totalAgents: workspaceTree.virtual_buckets.no_workspace.bot_count,
            agents: noWorkspaceAgents,
            squad: null,
          },
        ],
      });
    }

    for (const workspace of workspaceTree.items) {
      const workspaceMatches = matchesWorkspaceSearch(workspace, searchQuery);
      const lanes: BoardLane[] = [];
      const squadLanes: BoardLane[] = [];
      const noSquadAgents = filteredByLane.get(laneKey(workspace.id, null)) ?? [];
      const includeNoSquadLane =
        !searchQuery ||
        workspaceMatches ||
        noSquadAgents.length > 0 ||
        tl("Sem squad").toLowerCase().includes(searchQuery);

      const noSquadLane = includeNoSquadLane
        ? {
            key: laneKey(workspace.id, null),
            title: tl("Sem squad"),
            description:
              tl("Ponto de entrada do workspace para bots sem time definido."),
            workspaceId: workspace.id,
            squadId: null,
            totalAgents: workspace.virtual_buckets.no_squad.bot_count,
            agents: noSquadAgents,
            squad: null,
          }
        : null;

      for (const squad of workspace.squads) {
        const squadAgents =
          filteredByLane.get(laneKey(workspace.id, squad.id)) ?? [];
        const includeLane =
          !searchQuery ||
          workspaceMatches ||
          matchesSquadSearch(squad, searchQuery) ||
          squadAgents.length > 0;
        if (!includeLane) {
          continue;
        }
        squadLanes.push({
          key: laneKey(workspace.id, squad.id),
          title: squad.name,
          description:
            squad.description || tl("Time dedicado dentro deste workspace."),
          workspaceId: workspace.id,
          squadId: squad.id,
          totalAgents: squad.bot_count,
          agents: squadAgents,
          squad,
        });
      }

      if (squadLanes.length > 0) {
        lanes.push(...squadLanes);
      } else if (noSquadLane) {
        lanes.push(noSquadLane);
      }

      if (!searchQuery && squadLanes.length > 0 && noSquadLane) {
        while (lanes.length < MIN_WORKSPACE_LANES - 1) {
          const placeholderIndex = lanes.length;
          lanes.push({
            key: `${workspace.id}:__placeholder_${placeholderIndex}__`,
            title: tl("Nova squad"),
            description: tl("Espaço reservado para criar um novo time neste workspace."),
            workspaceId: workspace.id,
            squadId: null,
            totalAgents: 0,
            agents: [],
            squad: null,
            isPlaceholder: true,
          });
        }
        lanes.push(noSquadLane);
      } else if (noSquadLane && squadLanes.length > 0) {
        lanes.push(noSquadLane);
      }

      if (!searchQuery && (squadLanes.length === 0 || !noSquadLane)) {
        while (lanes.length < MIN_WORKSPACE_LANES) {
          const placeholderIndex = lanes.length;
          lanes.push({
            key: `${workspace.id}:__placeholder_${placeholderIndex}__`,
            title: tl("Nova squad"),
            description: tl("Espaço reservado para criar um novo time neste workspace."),
            workspaceId: workspace.id,
            squadId: null,
            totalAgents: 0,
            agents: [],
            squad: null,
            isPlaceholder: true,
          });
        }
      }

      const visibleAgents = lanes.reduce(
        (total, lane) => total + lane.agents.length,
        0,
      );
      if (!searchQuery || workspaceMatches || visibleAgents > 0) {
        sections.push({
          key: workspace.id,
          title: workspace.name,
          description:
            workspace.description ||
            tl("Organize squads e distribua os agentes deste workspace."),
          totalAgents: workspace.bot_count,
          visibleAgents,
          workspace,
          isVirtual: false,
          lanes,
        });
      }
    }

    return sections;
  }, [filteredAgents, searchQuery, tl, workspaceTree]);

  const workspaceTabs = useMemo(() => {
    const workspaceSections = boardSections.filter((section) => !section.isVirtual);
    const virtualSections = boardSections.filter((section) => section.isVirtual);
    return [...workspaceSections, ...virtualSections];
  }, [boardSections]);

  const activeSection = useMemo(() => {
    if (workspaceTabs.length === 0) {
      return null;
    }

    return (
      workspaceTabs.find((section) => section.key === activeSectionKey) ??
      workspaceTabs[0]
    );
  }, [activeSectionKey, workspaceTabs]);
  const tourVariant = workspaceTabs.length === 0 || !activeSection ? "empty" : "default";

  useEffect(() => {
    if (workspaceTabs.length === 0) {
      setActiveSectionKey(null);
      return;
    }

    setActiveSectionKey((current) => {
      if (current && workspaceTabs.some((section) => section.key === current)) {
        return current;
      }

      return (workspaceTabs.find((section) => !section.isVirtual) ?? workspaceTabs[0]).key;
    });
  }, [workspaceTabs]);

  async function refreshWorkspaces() {
    const nextTree = await requestJson("/api/control-plane/workspaces");
    setWorkspaceTree(nextTree as ControlPlaneWorkspaceTree);
    return nextTree as ControlPlaneWorkspaceTree;
  }

  const clearMoveFeedbackSoon = useCallback(() => {
    if (moveFeedbackTimerRef.current) {
      window.clearTimeout(moveFeedbackTimerRef.current);
    }

    moveFeedbackTimerRef.current = window.setTimeout(() => {
      setMoveFeedback(null);
      moveFeedbackTimerRef.current = null;
    }, 3200);
  }, []);

  function getLaneTargetLabel(lane: BoardLane) {
    if (!lane.workspaceId) {
        return tl("Sem workspace");
    }

    const workspace =
      workspaceTree.items.find((item) => item.id === lane.workspaceId) ?? null;
    const workspaceName = workspace?.name ?? tl("Workspace");

    if (!lane.squadId) {
      return `${workspaceName} / ${tl("Sem squad")}`;
    }

    return `${workspaceName} / ${lane.title}`;
  }

  function openWorkspaceForm(
    mode: "create" | "edit",
    workspace?: ControlPlaneWorkspace,
  ) {
    if (mode === "edit" && workspace) {
      setOrganizationForm({
        kind: "workspace",
        mode,
        targetId: workspace.id,
        name: workspace.name,
        description: workspace.description,
      });
      return;
    }
    setOrganizationForm({
      kind: "workspace",
      mode,
      name: "",
      description: "",
    });
  }

  function openSquadForm(
    workspace: ControlPlaneWorkspace,
    mode: "create" | "edit",
    squad?: ControlPlaneWorkspaceSquad,
  ) {
    if (mode === "edit" && squad) {
      setOrganizationForm({
        kind: "squad",
        mode,
        workspaceId: workspace.id,
        workspaceName: workspace.name,
        targetId: squad.id,
        name: squad.name,
        description: squad.description,
      });
      return;
    }
    setOrganizationForm({
      kind: "squad",
      mode,
      workspaceId: workspace.id,
      workspaceName: workspace.name,
      name: "",
      description: "",
    });
  }

  async function handleSubmitOrganizationForm() {
    if (!organizationForm) return;
    if (!organizationForm.name.trim()) {
      showToast(tl("O nome e obrigatorio."), "error");
      return;
    }

    setOrganizationBusy(true);
    try {
      if (organizationForm.kind === "workspace") {
        const path =
          organizationForm.mode === "create"
            ? "/api/control-plane/workspaces"
            : `/api/control-plane/workspaces/${organizationForm.targetId}`;
        const method = organizationForm.mode === "create" ? "POST" : "PATCH";
        await requestJson(path, {
          method,
          body: JSON.stringify({
            name: organizationForm.name,
            description: organizationForm.description,
          }),
        });
        showToast(
          organizationForm.mode === "create"
            ? tl("Workspace criado com sucesso.")
            : tl("Workspace atualizado com sucesso."),
          "success",
        );
      } else {
        if (!organizationForm.workspaceId) return;
        const path =
          organizationForm.mode === "create"
            ? `/api/control-plane/workspaces/${organizationForm.workspaceId}/squads`
            : `/api/control-plane/workspaces/${organizationForm.workspaceId}/squads/${organizationForm.targetId}`;
        const method = organizationForm.mode === "create" ? "POST" : "PATCH";
        await requestJson(path, {
          method,
          body: JSON.stringify({
            name: organizationForm.name,
            description: organizationForm.description,
          }),
        });
        showToast(
          organizationForm.mode === "create"
            ? tl("Squad criada com sucesso.")
            : tl("Squad atualizada com sucesso."),
          "success",
        );
      }

      await refreshWorkspaces();
      setOrganizationForm(null);
      router.refresh();
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : tl("Erro ao salvar organizacao."),
        "error",
      );
    } finally {
      setOrganizationBusy(false);
    }
  }

  async function handleDeleteTarget() {
    if (!deleteTarget) return;
    setOrganizationBusy(true);
    try {
      if (deleteTarget.kind === "workspace") {
        await requestJson(`/api/control-plane/workspaces/${deleteTarget.id}`, {
          method: "DELETE",
        });
        setCatalogAgents((current) =>
          current.map((agent) =>
            agent.organization?.workspace_id === deleteTarget.id
              ? {
                  ...agent,
                  organization: {
                    workspace_id: null,
                    workspace_name: null,
                    squad_id: null,
                    squad_name: null,
                  },
                }
              : agent,
          ),
        );
        showToast(tl("Workspace removido com sucesso."), "success");
      } else {
        if (deleteTarget.kind === "squad") {
          await requestJson(
            `/api/control-plane/workspaces/${deleteTarget.workspaceId}/squads/${deleteTarget.id}`,
            { method: "DELETE" },
          );
          setCatalogAgents((current) =>
            current.map((agent) =>
              agent.organization?.squad_id === deleteTarget.id
                ? {
                    ...agent,
                    organization: {
                      ...agent.organization,
                      squad_id: null,
                      squad_name: null,
                    },
                  }
                : agent,
            ),
          );
          showToast(tl("Squad removida com sucesso."), "success");
        } else {
          await requestJson(`/api/control-plane/agents/${deleteTarget.id}`, {
            method: "DELETE",
          });
          setCatalogAgents((current) =>
            current.filter((agent) => agent.id !== deleteTarget.id),
          );
          showToast(tl("Agente removido com sucesso."), "success");
        }
      }
      await refreshWorkspaces();
      setDeleteTarget(null);
      router.refresh();
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : tl("Erro ao remover organizacao."),
        "error",
      );
    } finally {
      setOrganizationBusy(false);
    }
  }

  async function handleMoveAgents(
    agentIds: string[],
    organization: OrganizationTarget,
    targetLabel: string,
  ) {
    const uniqueIds = [...new Set(agentIds)];
    const originalAgents = new Map(
      catalogAgents.map((agent) => [agent.id, agent] as const),
    );

    const moves = uniqueIds
      .map((agentId) => {
        const agent = originalAgents.get(agentId);
        if (!agent) {
          return null;
        }

        const from = {
          workspace_id: agent.organization?.workspace_id ?? null,
          squad_id: agent.organization?.workspace_id
            ? (agent.organization?.squad_id ?? null)
            : null,
        };

        if (sameOrganization(from, organization)) {
          return null;
        }

        return { agent, from, to: organization };
      })
      .filter((value): value is NonNullable<typeof value> => value !== null);

    if (moves.length === 0) {
      setDraggingBotIds([]);
      return;
    }

    const moveIds = moves.map((move) => move.agent.id);
    const moveIdSet = new Set(moveIds);
    const previewOrganization = buildOrganizationPreview(
      workspaceTree,
      organization,
    );

    if (moveFeedbackTimerRef.current) {
      window.clearTimeout(moveFeedbackTimerRef.current);
      moveFeedbackTimerRef.current = null;
    }

    setMovingBotIds((current) => [...new Set([...current, ...moveIds])]);
    setMoveFeedback({
      phase: "moving",
      total: moveIds.length,
      completed: 0,
      failed: 0,
      targetLabel,
    });
    setCatalogAgents((current) =>
      current.map((agent) =>
        moveIdSet.has(agent.id)
          ? {
              ...agent,
              organization: previewOrganization,
            }
          : agent,
      ),
    );
    setWorkspaceTree((current) =>
      applyBatchMoveToWorkspaceTree(
        current,
        moves.map((move) => ({ from: move.from, to: move.to })),
      ),
    );

    const successMap = new Map<string, ControlPlaneAgentSummary>();
    const failedMoves = new Map<
      string,
      { error: unknown; from: OrganizationTarget }
    >();

    await Promise.all(
      moves.map(async (move) => {
        try {
          const updated = (await requestJson(
            `/api/control-plane/agents/${move.agent.id}`,
            {
              method: "PATCH",
              body: JSON.stringify({ organization }),
            },
          )) as ControlPlaneAgentSummary;

          successMap.set(move.agent.id, updated);
        } catch (error) {
          failedMoves.set(move.agent.id, {
            error,
            from: move.from,
          });
        } finally {
          setMoveFeedback((current) =>
            current && current.phase === "moving"
              ? {
                  ...current,
                  completed: Math.min(current.completed + 1, current.total),
                  failed: failedMoves.size,
                }
              : current,
          );
        }
      }),
    );

    if (failedMoves.size > 0) {
      setCatalogAgents((current) =>
        current.map((agent) => {
          const updated = successMap.get(agent.id);
          if (updated) {
            return updated;
          }

          const failedMove = failedMoves.get(agent.id);
          if (!failedMove) {
            return agent;
          }

          return {
            ...agent,
            organization: buildOrganizationPreview(workspaceTree, failedMove.from),
          };
        }),
      );
    } else if (successMap.size > 0) {
      setCatalogAgents((current) =>
        current.map((agent) => successMap.get(agent.id) ?? agent),
      );
    }

    setMovingBotIds((current) => current.filter((id) => !moveIdSet.has(id)));
    setMoveFeedback({
      phase: "done",
      total: moveIds.length,
      completed: moveIds.length,
      failed: failedMoves.size,
      targetLabel,
    });

    await refreshWorkspaces();

    if (failedMoves.size === 0) {
      showToast(
        moveIds.length === 1
          ? tl("Agente movido para {{target}}.", { target: targetLabel })
          : tl("{{count}} agentes movidos para {{target}}.", { count: moveIds.length, target: targetLabel }),
        "success",
      );
    } else if (successMap.size > 0) {
      showToast(
        tl("{{moved}} agentes movidos e {{failed}} falharam.", {
          moved: successMap.size,
          failed: failedMoves.size,
        }),
        "warning",
      );
    } else {
      const firstFailure = failedMoves.values().next().value;
      showToast(
        firstFailure?.error instanceof Error
          ? firstFailure.error.message
          : tl("Nao foi possivel mover os agentes selecionados."),
        "error",
      );
    }

    clearMoveFeedbackSoon();
    router.refresh();
  }

  function scrollLaneRail(sectionKey: string, direction: -1 | 1) {
    const rail = laneRailRefs.current[sectionKey];
    if (!rail) return;
    const firstLane = rail.querySelector<HTMLElement>(
      "[data-lane-card='true']",
    );
    const laneWidth = firstLane?.offsetWidth ?? 360;
    rail.scrollBy({
      left: direction * (laneWidth + 16),
      behavior: "smooth",
    });
  }

  function handleLaneRailMouseDown(
    event: ReactMouseEvent<HTMLDivElement>,
    sectionKey: string,
  ) {
    if (event.button !== 0 || draggingBotIds.length > 0) {
      return;
    }
    if (!canStartLaneRailPan(event.target)) {
      return;
    }
    const rail = laneRailRefs.current[sectionKey];
    if (!rail) {
      return;
    }
    event.preventDefault();
    laneRailPanRef.current = {
      sectionKey,
      startX: event.clientX,
      initialScrollLeft: rail.scrollLeft,
    };
    setLaneRailDraggingKey(sectionKey);
  }

  function handleDragStart(agentId: string, dataTransfer: DataTransfer) {
    const dragIds = movingAgentIdSet.has(agentId) ? [] : [agentId];

    dataTransfer.effectAllowed = "move";
    dataTransfer.setData("text/plain", agentId);
    dataTransfer.setData(
      "application/json",
      JSON.stringify({ agentIds: dragIds }),
    );

    setDraggingBotIds(dragIds);
  }

  function handleDragEnd() {
    setDraggingBotIds([]);
    setDropTargetKey(null);
  }

  function readDraggedBotIds(dataTransfer: DataTransfer): string[] {
    if (draggingBotIds.length > 0) {
      return draggingBotIds;
    }

    const raw = dataTransfer.getData("application/json");
    if (raw) {
      try {
        const payload = JSON.parse(raw) as { agentIds?: string[] };
        if (Array.isArray(payload.agentIds) && payload.agentIds.length > 0) {
          return payload.agentIds.filter((value) => typeof value === "string");
        }
      } catch {
        // ignore malformed payload and fall back to plain text
      }
    }

    const agentId = dataTransfer.getData("text/plain");
    return agentId ? [agentId] : [];
  }

  function handleLaneDrop(event: DragEvent<HTMLElement>, lane: BoardLane) {
    event.preventDefault();
    const agentIds = readDraggedBotIds(event.dataTransfer);
    setDropTargetKey(null);
    setDraggingBotIds([]);

    if (agentIds.length === 0) {
      return;
    }

    const nextOrganization = {
      workspace_id: lane.workspaceId,
      squad_id: lane.workspaceId ? lane.squadId : null,
    };

    void handleMoveAgents(agentIds, nextOrganization, getLaneTargetLabel(lane));
  }

  function renderAgentCard(agent: ControlPlaneAgentSummary) {
    return (
      <AgentCatalogCard
        key={agent.id}
        agent={agent}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onEdit={(id) => router.push(`/control-plane/agents/${id}`)}
        onDuplicate={handleDuplicateAgent}
        onRequestDelete={(selectedAgent) =>
          setDeleteTarget({
            kind: "agent",
            id: selectedAgent.id,
            name: selectedAgent.display_name,
          })
        }
        busy={movingAgentIdSet.has(agent.id) || duplicatingBotId === agent.id}
        isDragging={draggingBotIds.includes(agent.id)}
        isMoving={movingAgentIdSet.has(agent.id)}
        isDuplicating={duplicatingBotId === agent.id}
      />
    );
  }

  async function handleDuplicateAgent(agent: ControlPlaneAgentSummary) {
    const cloneId = generateDuplicateBotId(agent.id);
    const cloneDisplayName = `${agent.display_name} (${tl("Copia")})`;
    setDuplicatingBotId(agent.id);
    try {
      const duplicated = (await requestJson(`/api/control-plane/agents/${agent.id}/clone`, {
        method: "POST",
        body: JSON.stringify({
          id: cloneId,
          display_name: cloneDisplayName,
        }),
      })) as ControlPlaneAgentSummary;

      const duplicatedAgent: ControlPlaneAgentSummary = {
        ...agent,
        ...duplicated,
        id: duplicated.id ?? cloneId,
        display_name: duplicated.display_name || cloneDisplayName,
        default_model_label:
          duplicated.default_model_label || agent.default_model_label,
        default_model_id: duplicated.default_model_id || agent.default_model_id,
      };

      setCatalogAgents((current) => [...current, duplicatedAgent]);
      await refreshWorkspaces();
      showToast(tl("Duplicata criada: {{id}}", { id: cloneId }), "success");
      router.refresh();
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : tl("Erro ao duplicar agente."),
        "error",
      );
    } finally {
      setDuplicatingBotId(null);
    }
  }

  return (
    <section className="agent-board flex min-h-0 flex-col gap-3 lg:h-full lg:gap-4" {...tourRoute("control-plane.catalog", tourVariant)}>
      <div className="agent-board-toolbar shrink-0">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="w-full md:min-w-[200px] md:flex-1" {...tourAnchor("catalog.search")}>
            <PageSearchField
              className="w-full"
              value={search}
              onChange={setSearch}
              placeholder={tl("Buscar por nome, ID, workspace ou squad...")}
              ariaLabel={tl("Buscar bots por nome, ID, workspace ou squad")}
            />
          </div>

          {activeSection && !activeSection.isVirtual && activeSection.workspace ? (
            <div
              className="flex h-10 items-center gap-1 self-start md:self-auto"
              {...tourAnchor("catalog.workspace-actions")}
            >
              <WorkspaceSpecIndicator
                hasPrompt={Boolean(
                  activeSection.workspace.documents?.system_prompt_md?.trim(),
                )}
              />
              <ActionButton
                type="button"
                size="icon"
                aria-label={tl("Configurar system prompt do espaco de trabalho {{workspace}}", { workspace: activeSection.workspace.name })}
                onClick={() =>
                  setWorkspaceSpecTarget({
                    id: activeSection.workspace!.id,
                    name: activeSection.workspace!.name,
                  })
                }
              >
                <FileText className="h-3.5 w-3.5" />
              </ActionButton>
              <ActionButton
                type="button"
                size="icon"
                aria-label={tl("Editar workspace {{workspace}}", { workspace: activeSection.workspace.name })}
                onClick={() =>
                  openWorkspaceForm("edit", activeSection.workspace!)
                }
              >
                <Pencil className="h-3.5 w-3.5" />
              </ActionButton>
              <ActionButton
                type="button"
                size="icon"
                aria-label={tl("Remover workspace {{workspace}}", { workspace: activeSection.workspace.name })}
                onClick={() =>
                  setDeleteTarget({
                    kind: "workspace",
                    id: activeSection.workspace!.id,
                    name: activeSection.workspace!.name,
                  })
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
              </ActionButton>
            </div>
          ) : null}

          <div
            className="field-shell flex h-10 items-center gap-1 self-start p-1 md:self-auto"
            style={{ width: "fit-content", borderRadius: "var(--radius-input)" }}
            {...tourAnchor("catalog.primary-actions")}
          >
            {workspaceTabs.length > 0 && (
              <WorkspaceSelectorDropdown
                workspaceTabs={workspaceTabs}
                activeSection={activeSection}
                onSelect={setActiveSectionKey}
                tl={tl}
              />
            )}
            <CreatePopover
              onCreateAgent={() => void createAgentViaHook()}
              onCreateWorkspace={() => openWorkspaceForm("create")}
              onCreateSquad={() => {
                if (activeSection?.workspace) {
                  openSquadForm(activeSection.workspace, "create");
                }
              }}
              hasActiveWorkspace={Boolean(activeSection && !activeSection.isVirtual)}
              tl={tl}
            />
          </div>
        </div>
      </div>

      <PageMetricStrip {...tourAnchor("catalog.metrics")}>
        <PageMetricStripItem
          label={tl("Bots")}
          value={metrics.totalAgents}
          hint={tl("Total no catálogo")}
        />
        <PageMetricStripItem
          label={tl("Active")}
          value={metrics.active}
          tone={metrics.active > 0 ? "accent" : "neutral"}
          hint={tl("Em execução agora")}
        />
        <PageMetricStripItem
          label={tl("Workspaces")}
          value={metrics.workspaces}
          hint={tl("Ambientes configurados")}
        />
        <PageMetricStripItem
          label={tl("Squads")}
          value={metrics.squads}
          hint={tl("Grupos dentro de workspaces")}
        />
      </PageMetricStrip>

      <AnimatePresence initial={false}>
        {moveFeedback ? (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className={`agent-board-bulk-strip ${
              moveFeedback?.phase === "moving"
                ? "agent-board-bulk-strip--moving"
                : ""
            }`}
          >
            <div className="agent-board-bulk-strip__content">
              <span className="agent-board-bulk-strip__icon" aria-hidden="true">
                {moveFeedback?.phase === "moving" ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCheck className="h-4 w-4" />
                )}
              </span>

              <div className="space-y-1">
                <p className="text-sm font-medium tracking-[-0.02em] text-[var(--text-primary)]">
                  {moveFeedback
                    .phase === "moving"
                    ? tl("Movendo {{count}} agente(s) para {{target}}", {
                        count: moveFeedback.total,
                        target: moveFeedback.targetLabel,
                      })
                    : moveFeedback.failed > 0
                      ? tl("{{done}} concluido(s) · {{failed}} falha(s)", {
                          done: moveFeedback.total - moveFeedback.failed,
                          failed: moveFeedback.failed,
                        })
                      : tl("{{count}} agente(s) sincronizado(s)", { count: moveFeedback.total })}
                </p>
                <p className="text-xs text-[var(--text-tertiary)]">
                  {moveFeedback
                    .phase === "moving"
                    ? tl("{{done}} de {{total}} atualizados em background. Você pode continuar navegando normalmente.", {
                        done: moveFeedback.completed,
                        total: moveFeedback.total,
                      })
                    : tl("Destino: {{target}}", { target: moveFeedback.targetLabel })}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {moveFeedback?.phase === "moving" ? (
                <span className="agent-board-bulk-strip__progress">
                  {moveFeedback.completed}/{moveFeedback.total}
                </span>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {activeSection ? (
        <div
          id={`workspace-panel-${activeSection.key}`}
          aria-label={activeSection.title}
          className="agent-board-shell flex min-h-0 flex-1 flex-col overflow-visible lg:overflow-hidden"
          {...tourAnchor("catalog.board")}
        >
            {activeSection.isVirtual ? (
              (() => {
                const lane = activeSection.lanes[0];
                const isDropTarget = dropTargetKey === lane?.key;

                return (
                    <div className="min-h-0 flex-1 overflow-hidden" {...tourAnchor("catalog.unassigned-lane")}>
                    <div
                      data-testid={`unassigned-grid-${activeSection.key}`}
                      onDragEnter={() => {
                        if (draggingBotIds.length > 0 && lane) {
                          setDropTargetKey(lane.key);
                        }
                      }}
                      onDragOver={(event) => {
                        if (draggingBotIds.length === 0 || !lane) return;
                        event.preventDefault();
                        if (dropTargetKey !== lane.key) {
                          setDropTargetKey(lane.key);
                        }
                      }}
                      onDrop={(event) => {
                        if (lane) {
                          void handleLaneDrop(event, lane);
                        }
                      }}
                      className={`agent-board-unassigned-grid h-full overflow-y-auto ${
                        isDropTarget
                          ? "agent-board-unassigned-grid--target"
                          : ""
                      }`}
                    >
                      {lane && lane.agents.length > 0 ? (
                        lane.agents.map(renderAgentCard)
                      ) : (
                        <div className="agent-board-unassigned-empty">
                          <p className="agent-board-empty__title">
                            {searchQuery
                              ? tl("Nenhum agente corresponde a esta busca.")
                              : tl("Sem agentes fora de workspace.")}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()
            ) : (
              <div className="flex min-h-0 flex-1 flex-col space-y-2">
                {activeSection.lanes.length > 3 ? (
                  <div className="flex shrink-0 items-center justify-end gap-2">
                    <ActionButton
                      type="button"
                      size="icon"
                      aria-label={tl("Mostrar squads anteriores de {{section}}", { section: activeSection.title })}
                      onClick={() => scrollLaneRail(activeSection.key, -1)}
                    >
                      ←
                    </ActionButton>
                    <ActionButton
                      type="button"
                      size="icon"
                      aria-label={tl("Mostrar mais squads de {{section}}", { section: activeSection.title })}
                      onClick={() => scrollLaneRail(activeSection.key, 1)}
                    >
                      →
                    </ActionButton>
                  </div>
                ) : null}

                <div
                  ref={(node) => {
                    laneRailRefs.current[activeSection.key] = node;
                  }}
                  data-testid={`lane-rail-${activeSection.key}`}
                  onMouseDown={(event) =>
                    handleLaneRailMouseDown(event, activeSection.key)
                  }
                    className={`catalog-lane-rail flex min-h-0 flex-1 items-stretch gap-4 overflow-x-auto pb-2 scroll-smooth snap-x snap-mandatory ${
                      laneRailDraggingKey === activeSection.key
                        ? "catalog-lane-rail--dragging"
                        : ""
                    }`}
                    {...tourAnchor("catalog.lanes")}
                  >
                  {activeSection.lanes.map((lane) => {
                    const isDropTarget = dropTargetKey === lane.key;
                    const laneWidth =
                      activeSection.lanes.length === 1
                        ? "100%"
                        : activeSection.lanes.length === 2
                          ? "calc((100% - 1rem) / 2)"
                          : activeSection.lanes.length === 3
                            ? "calc((100% - 2rem) / 3)"
                            : "clamp(18.5rem, 88vw, 30rem)";

                    return (
                      <section
                        key={lane.key}
                        data-lane-card="true"
                        data-testid={
                          lane.isPlaceholder
                            ? `lane-${lane.workspaceId ?? "no-workspace"}-placeholder-${lane.key}`
                            : `lane-${lane.workspaceId ?? "no-workspace"}-${lane.squadId ?? "no-squad"}`
                        }
                        onDragEnter={() => {
                          if (
                            draggingBotIds.length > 0 &&
                            !lane.isPlaceholder
                          ) {
                            setDropTargetKey(lane.key);
                          }
                        }}
                        onDragOver={(event) => {
                          if (
                            draggingBotIds.length === 0 ||
                            lane.isPlaceholder
                          )
                            return;
                          event.preventDefault();
                          if (dropTargetKey !== lane.key) {
                            setDropTargetKey(lane.key);
                          }
                        }}
                        onDrop={(event) => {
                          if (!lane.isPlaceholder) {
                            void handleLaneDrop(event, lane);
                          }
                        }}
                        className={`agent-board-lane flex h-full min-h-0 flex-shrink-0 snap-start flex-col rounded-[0.5rem] border transition-[border-color,background-color,box-shadow,transform] duration-200 ${
                          isDropTarget && !lane.isPlaceholder
                            ? "agent-board-lane--target"
                            : lane.isPlaceholder
                              ? "agent-board-lane--placeholder"
                              : "agent-board-lane--default"
                        } ${lane.isPlaceholder ? "px-4 py-4" : "overflow-hidden px-0 py-0"}`}
                        style={{ width: laneWidth }}
                      >
                        {!lane.isPlaceholder ? (
                          <div className="agent-board-lane__header agent-board-lane__header--plain">
                            <div className="agent-board-lane__heading">
                              <h3 className="agent-board-lane__title">
                                {lane.title}
                              </h3>
                            </div>

                            {lane.squad && activeSection.workspace ? (
                              <div className="agent-board-lane__actions">
                                <SquadSpecIndicator
                                  hasPrompt={Boolean(
                                    lane.squad.documents?.system_prompt_md?.trim(),
                                  )}
                                />
                                <ActionButton
                                  type="button"
                                  size="icon"
                                  className="agent-board-lane__action"
                                  aria-label={tl("Configurar system prompt do time {{squad}}", { squad: lane.squad.name })}
                                  onClick={() =>
                                    setSquadSpecTarget({
                                      workspaceId: activeSection.workspace!.id,
                                      squadId: lane.squad!.id,
                                      squadName: lane.squad!.name,
                                    })
                                  }
                                >
                                  <FileText className="h-3.5 w-3.5" />
                                </ActionButton>
                                <ActionButton
                                  type="button"
                                  size="icon"
                                  className="agent-board-lane__action"
                                  aria-label={tl("Editar squad {{squad}}", { squad: lane.squad.name })}
                                  onClick={() =>
                                    openSquadForm(
                                      activeSection.workspace!,
                                      "edit",
                                      lane.squad!,
                                    )
                                  }
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </ActionButton>
                                <ActionButton
                                  type="button"
                                  size="icon"
                                  className="agent-board-lane__action agent-board-lane__action--danger"
                                  aria-label={tl("Remover squad {{squad}}", { squad: lane.squad.name })}
                                  onClick={() =>
                                    setDeleteTarget({
                                      kind: "squad",
                                      id: lane.squad!.id,
                                      name: lane.squad!.name,
                                      workspaceId: activeSection.workspace!.id,
                                    })
                                  }
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </ActionButton>
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="text-base font-medium tracking-[-0.03em] text-[var(--text-primary)]">
                                  {lane.title}
                                </h3>
                              </div>
                            </div>
                          </div>
                        )}

                        <div className={`${lane.isPlaceholder ? "mt-4" : ""} flex min-h-0 flex-1 flex-col gap-2 ${lane.isPlaceholder ? "" : "px-2.5 py-2"}`}>
                          {lane.agents.length > 0 ? (
                            <div className="agent-board-list">
                              {lane.agents.map(renderAgentCard)}
                            </div>
                          ) : lane.isPlaceholder && activeSection.workspace ? (
                              <div className="agent-board-slot flex min-h-0 flex-1 flex-col items-center justify-center rounded-[0.5rem] px-6 py-8 text-center" {...tourAnchor("catalog.placeholder-lane")}>
                              <p className="agent-board-empty__title">
                                {tl("Sem squads ainda")}
                              </p>
                              <ActionButton
                                type="button"
                                className="agent-board-slot__action"
                                onClick={() =>
                                  openSquadForm(activeSection.workspace!, "create")
                                }
                              >
                                <Plus className="h-4 w-4" />
                                {tl("Adicionar squad")}
                              </ActionButton>
                            </div>
                          ) : (
                            <div className="agent-board-empty flex min-h-0 flex-1 flex-col items-center justify-center rounded-[0.5rem] px-6 py-8 text-center" {...tourAnchor("catalog.empty-lane")}>
                              <p className="agent-board-empty__title">
                                {searchQuery
                                  ? tl("Nenhum agente corresponde a esta busca.")
                                  : tl("Sem agentes neste squad.")}
                              </p>
                            </div>
                          )}
                        </div>
                      </section>
                    );
                  })}
                </div>
              </div>
            )}
        </div>
      ) : (
        <div className="min-h-[220px] px-6 py-10" {...tourAnchor("catalog.empty")}>
          <div className="agent-board-global-empty">
            <p className="agent-board-empty__title">
              {tl("Nenhum agente encontrado.")}
            </p>
          </div>
        </div>
      )}

      {organizationForm ? (
        <>
          <div
            className="app-overlay-backdrop z-[70]"
            onClick={() => setOrganizationForm(null)}
            aria-hidden="true"
          />
          <div className="app-modal-frame z-[80] flex items-center justify-center overflow-auto px-4 py-8">
          <div
            className="app-modal-panel agent-board-dialog w-full max-w-lg p-5 sm:p-6"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2">
                <p className="eyebrow">
                  {organizationForm.kind === "workspace"
                    ? tl("Workspace")
                    : tl("Squad")}
                </p>
                <h3 className="text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                  {organizationForm.mode === "create"
                    ? organizationForm.kind === "workspace"
                      ? tl("Criar novo workspace")
                      : tl("Criar squad em {{workspace}}", { workspace: organizationForm.workspaceName })
                    : organizationForm.kind === "workspace"
                      ? tl("Editar workspace")
                      : tl("Editar squad")}
                </h3>
                <p className="text-sm text-[var(--text-tertiary)]">
                  {tl("Defina nome, descricao curta e a cor de apoio visual desta organizacao.")}
                </p>
              </div>
              <button
                type="button"
                className="agent-board-inline-action"
                aria-label={tl("Fechar formulario")}
                onClick={() => setOrganizationForm(null)}
                disabled={organizationBusy}
              >
                {tl("Fechar")}
              </button>
            </div>

            <div className="mt-6 space-y-4">
              <FormInput
                label={
                  organizationForm.kind === "workspace"
                    ? tl("Nome do workspace")
                    : tl("Nome da squad")
                }
                value={organizationForm.name}
                onChange={(event) =>
                  setOrganizationForm((current) =>
                    current
                      ? { ...current, name: event.target.value }
                      : current,
                  )
                }
                placeholder={
                  organizationForm.kind === "workspace"
                    ? tl("Ex.: Produto")
                    : tl("Ex.: Plataforma")
                }
              />
              <FormInput
                label={tl("Descricao")}
                value={organizationForm.description}
                onChange={(event) =>
                  setOrganizationForm((current) =>
                    current
                      ? { ...current, description: event.target.value }
                      : current,
                  )
                }
                placeholder={tl("Descricao curta opcional")}
              />
            </div>

              <div className="mt-6 flex items-center justify-end gap-2">
                <ActionButton
                  type="button"
                  onClick={() => setOrganizationForm(null)}
                  disabled={organizationBusy}
                >
                {tl("Cancelar")}
              </ActionButton>
              <ActionButton
                type="button"
                loading={organizationBusy}
                onClick={() => void handleSubmitOrganizationForm()}
                disabled={organizationBusy}
              >
                {organizationBusy
                  ? tl("Salvando...")
                  : organizationForm.mode === "create"
                    ? tl("Criar")
                    : tl("Salvar")}
              </ActionButton>
            </div>
          </div>
          </div>
        </>
      ) : null}

      <ConfirmationDialog
        open={deleteTarget !== null}
        title={
          deleteTarget?.kind === "workspace"
            ? tl("Remover workspace")
            : deleteTarget?.kind === "squad"
              ? tl("Remover squad")
              : tl("Remover agente")
        }
        message={
          deleteTarget?.kind === "workspace"
            ? tl('Ao remover "{{name}}", os agents vinculados voltam para Sem workspace.', { name: deleteTarget.name })
            : deleteTarget?.kind === "squad"
              ? tl('Ao remover "{{name}}", os agents vinculados continuam no workspace atual e voltam para Sem squad.', { name: deleteTarget?.name })
              : tl('Tem certeza que deseja remover "{{name}}"? Todas as configuracoes, documentos e versoes serao permanentemente excluidos. Esta acao nao pode ser desfeita.', { name: deleteTarget?.name })
        }
        confirmLabel={tl("Remover")}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDeleteTarget()}
      />

      {workspaceSpecTarget ? (
        <WorkspaceSpecEditor
          workspaceId={workspaceSpecTarget.id}
          workspaceName={workspaceSpecTarget.name}
          open
          onClose={() => setWorkspaceSpecTarget(null)}
        />
      ) : null}

      {squadSpecTarget ? (
        <SquadSpecEditor
          workspaceId={squadSpecTarget.workspaceId}
          squadId={squadSpecTarget.squadId}
          squadName={squadSpecTarget.squadName}
          open
          onClose={() => setSquadSpecTarget(null)}
        />
      ) : null}
    </section>
  );
}
