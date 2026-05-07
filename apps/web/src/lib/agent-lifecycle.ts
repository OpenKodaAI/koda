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
  /** Short label for badges/headers ("Ativo", "Publicado · Pausado" etc). */
  label: string;
  /** Long-form explanation displayed under the status badge. */
  description: string;
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
      label: "Alterações não publicadas",
      description:
        "Há mudanças no editor que ainda não foram publicadas. Salve e publique para aplicá-las ao runtime.",
      tone: "warning",
      pulse: true,
      toggle: status === "active" ? "pause" : "activate",
    };
  }

  // 2. First-time draft — agent was created but no version exists yet.
  if (dirty && applied === null && desired === null) {
    return {
      id: "draft_unsaved",
      label: "Rascunho não publicado",
      description:
        "Configuração inicial em andamento. Publique pela primeira vez para tornar o agente operável.",
      tone: "warning",
      pulse: true,
      toggle: "none",
    };
  }

  // 3. Agent created via seed / clone but never touched.
  if (!dirty && applied === null && desired === null) {
    return {
      id: "never_configured",
      label: "Nunca publicado",
      description:
        "O agente foi criado mas ainda não tem nenhuma versão publicada. Configure e publique para ativar.",
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
      label: "Publicado, aguardando ativação",
      description:
        "Versão publicada mas o runtime ainda não foi inicializado. Clique em Ativar para colocar o agente para rodar.",
      tone: "info",
      pulse: true,
      toggle: "activate",
    };
  }

  // 5. New version published but the runtime is still serving an older one.
  if (!dirty && applied !== null && desired !== null && applied < desired) {
    return {
      id: "update_pending",
      label: "Atualização pendente",
      description: `Runtime rodando a v${applied}, mas a v${desired} já foi publicada e aguarda aplicação.`,
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
      label: "Ativo",
      description: `Runtime rodando v${applied} normalmente. Mensagens são processadas.`,
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
      label: "Publicado · Pausado",
      description: `Versão v${applied} publicada mas o runtime está pausado. Mensagens não são processadas.`,
      tone: "info",
      pulse: false,
      toggle: "activate",
    };
  }

  return {
    id: "unknown",
    label: status ? `Status: ${status}` : "Estado desconhecido",
    description:
      "Estado não previsto pelo wizard de publicação. Consulte os logs do control-plane se persistir.",
    tone: "neutral",
    pulse: false,
    toggle: "none",
  };
}
