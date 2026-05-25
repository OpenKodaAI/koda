/**
 * Agent lifecycle state — derives a single, granular status from the three
 * raw signals exposed by the control-plane:
 *
 *   - `cp_agent_definitions.status`        (runtime: active | paused | …)
 *   - `cp_agent_definitions.applied_version`  (version currently bootstrapped)
 *   - `cp_agent_definitions.desired_version`  (latest published version)
 *
 *   - `state.dirty`                       (frontend: in-progress edits)
 *
 * The helper centralises the rules so the editor header, the publication tab
 * and any future surface (catalog cards, dashboard etc.) display the same
 * narrative regardless of how the underlying flags happened to land.
 */

export type AgentLifecycleTone = "neutral" | "warning" | "info" | "success";

export type AgentLifecycleId =
  | "never_configured"
  | "draft_unsaved"
  | "draft_pending_publish"
  | "awaiting_activation"
  | "update_pending"
  | "published_active"
  | "published_paused"
  | "unknown";

export interface AgentLifecycleState {
  id: AgentLifecycleId;
  /** Short translated label key for badges/headers. */
  labelKey: string;
  /** Long-form translated explanation key displayed under the status badge. */
  descriptionKey: string;
  descriptionOptions?: Record<string, string | number>;
  tone: AgentLifecycleTone;
  /** Whether the StatusDot should pulse (warns the operator). */
  pulse: boolean;
  /**
   *   "activate" — agent runtime is paused (or awaiting first activation);
   *                show the Ativar button.
   *   "pause"    — agent runtime is active; show the Pausar button.
   *   "none"     — agent has never been published or has unsaved drafts on a
   *                blank slate; activation is not yet meaningful.
   */
  toggle: "activate" | "pause" | "none";
}

export interface AgentLifecycleInputs {
  status: string | null | undefined;
  appliedVersion: number | null | undefined;
  desiredVersion: number | null | undefined;
  hasPendingChanges: boolean;
}

export function getAgentLifecycleState(
  input: AgentLifecycleInputs,
): AgentLifecycleState {
  const status = (input.status || "").toLowerCase();
  const applied = input.appliedVersion ?? null;
  const desired = input.desiredVersion ?? null;
  const dirty = input.hasPendingChanges;

  // 1. Local edits over an already-published agent — the runtime is still
  //    on the previous version; the operator must publish to roll forward.
  if (dirty && (applied !== null || desired !== null)) {
    return {
      id: "draft_pending_publish",
      labelKey: "controlPlane.agentLifecycle.draftPendingPublish.label",
      descriptionKey: "controlPlane.agentLifecycle.draftPendingPublish.description",
      tone: "warning",
      pulse: true,
      toggle: status === "active" ? "pause" : "activate",
    };
  }

  // 2. First-time draft — agent was created but no version exists yet.
  if (dirty && applied === null && desired === null) {
    return {
      id: "draft_unsaved",
      labelKey: "controlPlane.agentLifecycle.draftUnsaved.label",
      descriptionKey: "controlPlane.agentLifecycle.draftUnsaved.description",
      tone: "warning",
      pulse: true,
      toggle: "none",
    };
  }

  // 3. Agent created via seed / clone but never touched.
  if (!dirty && applied === null && desired === null) {
    return {
      id: "never_configured",
      labelKey: "controlPlane.agentLifecycle.neverConfigured.label",
      descriptionKey: "controlPlane.agentLifecycle.neverConfigured.description",
      tone: "neutral",
      pulse: false,
      toggle: "none",
    };
  }

  // 4. Published but the runtime never bootstrapped — applied=null while
  //    desired is set. Operator needs to click Ativar.
  if (!dirty && applied === null && desired !== null) {
    return {
      id: "awaiting_activation",
      labelKey: "controlPlane.agentLifecycle.awaitingActivation.label",
      descriptionKey: "controlPlane.agentLifecycle.awaitingActivation.description",
      tone: "info",
      pulse: true,
      toggle: "activate",
    };
  }

  // 5. New version published but the runtime is still serving an older one.
  if (!dirty && applied !== null && desired !== null && applied < desired) {
    return {
      id: "update_pending",
      labelKey: "controlPlane.agentLifecycle.updatePending.label",
      descriptionKey: "controlPlane.agentLifecycle.updatePending.description",
      descriptionOptions: { applied, desired },
      tone: "warning",
      pulse: true,
      toggle: status === "active" ? "pause" : "activate",
    };
  }

  // 6. Steady-state: applied = desired and runtime active.
  if (
    !dirty &&
    applied !== null &&
    applied === desired &&
    status === "active"
  ) {
    return {
      id: "published_active",
      labelKey: "controlPlane.agentLifecycle.publishedActive.label",
      descriptionKey: "controlPlane.agentLifecycle.publishedActive.description",
      descriptionOptions: { applied },
      tone: "success",
      pulse: false,
      toggle: "pause",
    };
  }

  // 7. Steady-state but runtime paused by the operator.
  if (
    !dirty &&
    applied !== null &&
    applied === desired &&
    status === "paused"
  ) {
    return {
      id: "published_paused",
      labelKey: "controlPlane.agentLifecycle.publishedPaused.label",
      descriptionKey: "controlPlane.agentLifecycle.publishedPaused.description",
      descriptionOptions: { applied },
      tone: "info",
      pulse: false,
      toggle: "activate",
    };
  }

  return {
    id: "unknown",
    labelKey: status
      ? "controlPlane.agentLifecycle.unknown.label"
      : "controlPlane.agentLifecycle.unknown.labelFallback",
    descriptionKey: "controlPlane.agentLifecycle.unknown.description",
    descriptionOptions: status ? { status } : undefined,
    tone: "neutral",
    pulse: false,
    toggle: "none",
  };
}
