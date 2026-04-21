"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useEffect,
  type ReactNode,
} from "react";
import { useLocalStorage } from "@/hooks/use-local-storage";
import {
  buildAgentSpecPayload,
  buildAgentMetadataPayload,
  parseJsonArray,
  prettyJson,
} from "@/lib/control-plane-editor";
import {
  normalizeModelPolicyForCore,
  parseModelPolicy,
  serializeModelPolicy,
} from "@/lib/policy-serializers";
import type {
  ControlPlaneAgent,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCoreIntegrations,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneExecutionPolicyPayload,
  ControlPlaneSystemSettings,
  ControlPlaneCoreTools,
  ScopePromptDocuments,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export type EditorState = {
  agent: ControlPlaneAgent;
  // Meta fields
  displayName: string;
  status: string;
  storageNamespace: string;
  workspaceId: string;
  squadId: string;
  color: string;
  colorRgb: string;
  healthPort: string;
  healthUrl: string;
  runtimeBaseUrl: string;
  appearanceJson: string;
  runtimeEndpointJson: string;
  metadataJson: string;
  // Documents
  documents: Record<string, string>;
  // Agent spec fields (all as JSON strings)
  missionProfileJson: string;
  interactionStyleJson: string;
  operatingInstructionsJson: string;
  hardRulesJson: string;
  responsePolicyJson: string;
  modelPolicyJson: string;
  toolPolicyJson: string;
  memoryPolicyJson: string;
  knowledgePolicyJson: string;
  autonomyPolicyJson: string;
  executionPolicyJson: string;
  executionPolicyPayload: ControlPlaneExecutionPolicyPayload | null;
  resourceAccessPolicyJson: string;
  voicePolicyJson: string;
  imageAnalysisPolicyJson: string;
  memoryExtractionSchemaJson: string;
  skillPolicyJson: string;
  customSkillsJson: string;
  // Sections
  sectionsJson: string;
  // Collections
  knowledgeJson: string;
  templatesJson: string;
  skillsJson: string;
  // Publishing
  compiledPrompt: string;
  compiledPromptPayload: ControlPlaneCompiledPrompt | null;
  validationJson: string;
  // Secrets
  secretKey: string;
  secretValue: string;
  secretScope: string;
  // Clone
  cloneId: string;
  cloneDisplayName: string;
  // Governance
  knowledgeCandidatesJson: string;
  runbooksJson: string;
  candidateActionId: string;
  runbookActionId: string;
  executionPolicyDirty: boolean;
  // Dirty tracking
  dirty: Record<string, boolean>;
};

type PersistDraftOptions = {
  includeMeta?: boolean;
  includeAgentSpec?: boolean;
  includeCollections?: boolean;
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

type EditorAction =
  | { type: "updateField"; field: keyof EditorState; value: unknown }
  | { type: "updateDocument"; key: string; value: string }
  | { type: "updateAgentSpecField"; key: string; value: string }
  | { type: "updateSectionJson"; value: string }
  | { type: "updateCollectionJson"; kind: string; value: string }
  | { type: "resetDirty"; section: string }
  | { type: "setCompiledPrompt"; value: string }
  | { type: "setCompiledPromptPayload"; value: ControlPlaneCompiledPrompt | null }
  | { type: "setValidationJson"; value: string }
  | {
      type: "hydrateAgent";
      agent: ControlPlaneAgent;
      compiledPromptPayload?: ControlPlaneCompiledPrompt | null;
      executionPolicyPayload?: ControlPlaneExecutionPolicyPayload | null;
    };

// ---------------------------------------------------------------------------
// Dirty-section mapping
// ---------------------------------------------------------------------------

const META_FIELDS = new Set<string>([
  "displayName",
  "status",
  "storageNamespace",
  "workspaceId",
  "squadId",
  "color",
  "colorRgb",
  "healthPort",
  "healthUrl",
  "runtimeBaseUrl",
  "appearanceJson",
  "runtimeEndpointJson",
  "metadataJson",
]);

const AGENT_SPEC_FIELDS = new Set<string>([
  "missionProfileJson",
  "interactionStyleJson",
  "operatingInstructionsJson",
  "hardRulesJson",
  "responsePolicyJson",
  "modelPolicyJson",
  "toolPolicyJson",
  "memoryPolicyJson",
  "knowledgePolicyJson",
  "autonomyPolicyJson",
  "executionPolicyJson",
  "resourceAccessPolicyJson",
  "voicePolicyJson",
  "imageAnalysisPolicyJson",
  "memoryExtractionSchemaJson",
]);

const COLLECTION_TO_DIRTY: Record<string, string> = {
  knowledgeJson: "collections",
  templatesJson: "collections",
  skillsJson: "collections",
};

function dirtySection(field: string): string | null {
  if (META_FIELDS.has(field)) return "meta";
  if (AGENT_SPEC_FIELDS.has(field)) return "agentSpec";
  if (field === "sectionsJson") return "sections";
  if (COLLECTION_TO_DIRTY[field]) return "collections";
  return null;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function reducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "updateField": {
      const section = dirtySection(action.field as string);
      return {
        ...state,
        [action.field]: action.value,
        dirty: section
          ? { ...state.dirty, [section]: true }
          : state.dirty,
      };
    }

    case "updateDocument": {
      return {
        ...state,
        documents: { ...state.documents, [action.key]: action.value },
        dirty: { ...state.dirty, documents: true },
      };
    }

    case "updateAgentSpecField": {
      return {
        ...state,
        [action.key]: action.value,
        dirty: { ...state.dirty, agentSpec: true },
        ...(action.key === "executionPolicyJson" ? { executionPolicyDirty: true } : {}),
      };
    }

    case "updateSectionJson": {
      return {
        ...state,
        sectionsJson: action.value,
        dirty: { ...state.dirty, sections: true },
      };
    }

    case "updateCollectionJson": {
      const fieldMap: Record<string, string> = {
        knowledge: "knowledgeJson",
        templates: "templatesJson",
        skills: "skillsJson",
      };
      const field = fieldMap[action.kind];
      if (!field) return state;
      return {
        ...state,
        [field]: action.value,
        dirty: { ...state.dirty, collections: true },
      };
    }

    case "resetDirty": {
      return {
        ...state,
        dirty: { ...state.dirty, [action.section]: false },
      };
    }

    case "setCompiledPrompt": {
      return { ...state, compiledPrompt: action.value };
    }

    case "setCompiledPromptPayload": {
      return {
        ...state,
        compiledPromptPayload: action.value,
        compiledPrompt: action.value?.compiled_prompt || state.compiledPrompt,
      };
    }

    case "setValidationJson": {
      return { ...state, validationJson: action.value };
    }

    case "hydrateAgent": {
      const nextState = buildInitialState(
        action.agent,
        action.compiledPromptPayload,
        action.executionPolicyPayload,
      );
      return {
        ...nextState,
        secretKey: state.secretKey,
        secretValue: state.secretValue,
        secretScope: state.secretScope,
        cloneId: state.cloneId,
        cloneDisplayName: state.cloneDisplayName,
        candidateActionId: state.candidateActionId,
        runbookActionId: state.runbookActionId,
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Initial state builder
// ---------------------------------------------------------------------------

function normalizeCompiledPromptPayload(
  agent: ControlPlaneAgent,
  payload?: ControlPlaneCompiledPrompt | null,
): ControlPlaneCompiledPrompt | null {
  if (payload) {
    return payload;
  }

  if (!agent.compiled_prompt && !agent.validation?.compiled_prompt) {
    return null;
  }

  return {
    bot_id: agent.id,
    compiled_prompt: agent.compiled_prompt || agent.validation?.compiled_prompt || "",
    documents: agent.validation?.documents ?? {},
    document_sources: agent.validation?.document_sources,
    sections_present: agent.validation?.sections_present,
    document_lengths: agent.validation?.document_lengths,
    prompt_preview: agent.validation?.prompt_preview,
    agent_contract_prompt_preview:
      agent.validation?.agent_contract_prompt_preview ?? agent.validation?.bot_contract_prompt_preview,
    bot_contract_prompt_preview:
      agent.validation?.agent_contract_prompt_preview ?? agent.validation?.bot_contract_prompt_preview,
    runtime_prompt_preview: agent.validation?.runtime_prompt_preview,
  };
}

function buildInitialState(
  agent: ControlPlaneAgent,
  compiledPromptPayload?: ControlPlaneCompiledPrompt | null,
  executionPolicyPayload?: ControlPlaneExecutionPolicyPayload | null,
): EditorState {
  // Backend may omit runtime_endpoint / agent_spec for archived agents or
  // during transient error states. Default to empty objects so we don't
  // crash with "Cannot read properties of null (reading 'health_port')".
  const rt = (agent.runtime_endpoint ?? {}) as Record<string, unknown>;
  const spec = (agent.agent_spec ?? {}) as Record<string, unknown>;
  const normalizedCompiledPromptPayload = normalizeCompiledPromptPayload(agent, compiledPromptPayload);
  const normalizedExecutionPolicyPayload = executionPolicyPayload ?? null;
  const effectiveExecutionPolicy =
    normalizedExecutionPolicyPayload?.policy ?? (spec.execution_policy as Record<string, unknown> | undefined) ?? {};

  return {
    agent,
    // Meta
    displayName: agent.display_name,
    status: agent.status,
    storageNamespace: agent.storage_namespace,
    workspaceId: agent.organization?.workspace_id ?? "",
    squadId: agent.organization?.squad_id ?? "",
    color: agent.appearance?.color ?? "",
    colorRgb: agent.appearance?.color_rgb ?? "",
    healthPort: String(rt.health_port ?? ""),
    healthUrl: String(rt.health_url ?? ""),
    runtimeBaseUrl: String(rt.runtime_base_url ?? ""),
    appearanceJson: prettyJson(agent.appearance ?? {}),
    runtimeEndpointJson: prettyJson(agent.runtime_endpoint ?? {}),
    metadataJson: prettyJson(agent.metadata ?? {}),
    // Documents — the backend may legitimately omit this for new agents.
    // Spreading null throws; the empty-object fallback keeps the editor
    // mountable for agents that haven't been fully initialized yet.
    documents: { ...(agent.documents ?? {}) },
    // Agent spec
    missionProfileJson: prettyJson(spec.mission_profile ?? {}),
    interactionStyleJson: prettyJson(spec.interaction_style ?? {}),
    operatingInstructionsJson: prettyJson(spec.operating_instructions ?? {}),
    hardRulesJson: prettyJson(spec.hard_rules ?? {}),
    responsePolicyJson: prettyJson(spec.response_policy ?? {}),
    modelPolicyJson: prettyJson(spec.model_policy ?? {}),
    toolPolicyJson: prettyJson(spec.tool_policy ?? {}),
    memoryPolicyJson: prettyJson(spec.memory_policy ?? {}),
    knowledgePolicyJson: prettyJson(spec.knowledge_policy ?? {}),
    autonomyPolicyJson: prettyJson(spec.autonomy_policy ?? {}),
    executionPolicyJson: prettyJson(effectiveExecutionPolicy),
    executionPolicyPayload: normalizedExecutionPolicyPayload,
    resourceAccessPolicyJson: prettyJson(spec.resource_access_policy ?? {}),
    voicePolicyJson: prettyJson(spec.voice_policy ?? {}),
    imageAnalysisPolicyJson: prettyJson(spec.image_analysis_policy ?? {}),
    memoryExtractionSchemaJson: prettyJson(spec.memory_extraction_schema ?? {}),
    skillPolicyJson: prettyJson(spec.skill_policy ?? {}),
    customSkillsJson: prettyJson(spec.custom_skills ?? []),
    // Sections
    sectionsJson: prettyJson(agent.sections),
    // Collections
    knowledgeJson: prettyJson(agent.knowledge_assets),
    templatesJson: prettyJson(agent.templates),
    skillsJson: prettyJson(agent.skills),
    // Publishing
    compiledPrompt: normalizedCompiledPromptPayload?.compiled_prompt || agent.compiled_prompt,
    compiledPromptPayload: normalizedCompiledPromptPayload,
    validationJson: prettyJson(agent.validation),
    // Secrets
    secretKey: "",
    secretValue: "",
    secretScope: "",
    // Clone
    cloneId: "",
    cloneDisplayName: "",
    // Governance
    knowledgeCandidatesJson: prettyJson(agent.knowledge_candidates ?? []),
    runbooksJson: prettyJson(agent.runbooks ?? []),
    candidateActionId: "",
    runbookActionId: "",
    executionPolicyDirty: false,
    // Dirty
    dirty: {
      meta: false,
      documents: false,
      agentSpec: false,
      sections: false,
      collections: false,
    },
  };
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export type InheritedSpecs = {
  workspaceDocuments: ScopePromptDocuments;
  workspaceSystemPrompt: string;
  squadDocuments: ScopePromptDocuments;
  squadSystemPrompt: string;
  loading: boolean;
};

type AgentEditorContextValue = {
  state: EditorState;
  developerMode: boolean;
  setDeveloperMode: (value: boolean | ((prev: boolean) => boolean)) => void;
  core: {
    tools: ControlPlaneCoreTools;
    providers: ControlPlaneCoreProviders;
    policies: ControlPlaneCorePolicies;
    capabilities: ControlPlaneCoreCapabilities;
    integrations?: ControlPlaneCoreIntegrations;
  };
  workspaces: ControlPlaneWorkspaceTree;
  systemSettings: ControlPlaneSystemSettings;
  inherited: InheritedSpecs;
  dispatch: React.Dispatch<EditorAction>;
  updateField: (field: keyof EditorState, value: unknown) => void;
  updateDocument: (key: string, value: string) => void;
  updateAgentSpecField: (key: string, value: string) => void;
  updateSectionJson: (value: string) => void;
  updateCollectionJson: (kind: string, value: string) => void;
  resetDirty: (section: string) => void;
  setCompiledPrompt: (value: string) => void;
  setCompiledPromptPayload: (value: ControlPlaneCompiledPrompt | null) => void;
  setValidationJson: (value: string) => void;
  executionPolicyPayload: ControlPlaneExecutionPolicyPayload | null;
  refreshCompiledPrompt: () => Promise<ControlPlaneCompiledPrompt>;
  discardDraft: () => void;
  persistDraft: (options?: PersistDraftOptions) => Promise<{ persisted: string[] }>;
};

const AgentEditorContext = createContext<AgentEditorContextValue | null>(null);

async function requestJson<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
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
  return payload as T;
}

export function AgentEditorProvider({
  agent,
  compiledPromptPayload,
  executionPolicyPayload,
  core,
  workspaces,
  systemSettings,
  children,
}: {
  agent: ControlPlaneAgent;
  compiledPromptPayload?: ControlPlaneCompiledPrompt | null;
  executionPolicyPayload?: ControlPlaneExecutionPolicyPayload | null;
  core: {
    tools: ControlPlaneCoreTools;
    providers: ControlPlaneCoreProviders;
    policies: ControlPlaneCorePolicies;
    capabilities: ControlPlaneCoreCapabilities;
    integrations?: ControlPlaneCoreIntegrations;
  };
  workspaces: ControlPlaneWorkspaceTree;
  systemSettings: ControlPlaneSystemSettings;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(
    reducer,
    { agent, compiledPromptPayload, executionPolicyPayload },
    ({
      agent: initialAgent,
      compiledPromptPayload: initialCompiledPromptPayload,
      executionPolicyPayload: initialExecutionPolicyPayload,
    }) =>
      buildInitialState(
        initialAgent,
        initialCompiledPromptPayload,
        initialExecutionPolicyPayload,
      ),
  );
  const [developerMode, setDeveloperMode] = useLocalStorage<boolean>(
    "ui:agent-editor:developer-mode",
    false,
  );

  // Inherited workspace / squad specs
  const [inherited, setInherited] = React.useState<InheritedSpecs>({
    workspaceDocuments: {},
    workspaceSystemPrompt: "",
    squadDocuments: {},
    squadSystemPrompt: "",
    loading: false,
  });

  useEffect(() => {
    dispatch({ type: "hydrateAgent", agent, compiledPromptPayload, executionPolicyPayload });
  }, [agent, compiledPromptPayload, executionPolicyPayload]);

  // Fetch workspace and squad specs when the agent's organization changes
  useEffect(() => {
    const workspaceId = agent.organization?.workspace_id;
    const squadId = agent.organization?.squad_id;
    let cancelled = false;

    const fetchSpecs = async () => {
      if (!workspaceId) {
        if (!cancelled) {
          setInherited({
            workspaceDocuments: {},
            workspaceSystemPrompt: "",
            squadDocuments: {},
            squadSystemPrompt: "",
            loading: false,
          });
        }
        return;
      }

      if (!cancelled) {
        setInherited((prev) => ({ ...prev, loading: true }));
      }

      let workspaceDocuments: ScopePromptDocuments = {};
      let workspaceSystemPrompt = "";
      let squadDocuments: ScopePromptDocuments = {};
      let squadSystemPrompt = "";

      try {
        const wsResult = await requestJson<{
          documents: ScopePromptDocuments;
        }>(`/api/control-plane/workspaces/${workspaceId}/spec`);
        workspaceDocuments = wsResult.documents ?? {};
        workspaceSystemPrompt = String(wsResult.documents?.system_prompt_md || "");
      } catch {
        // Workspace prompt not available.
      }

      if (squadId) {
        try {
          const sqResult = await requestJson<{
            documents: ScopePromptDocuments;
          }>(
            `/api/control-plane/workspaces/${workspaceId}/squads/${squadId}/spec`,
          );
          squadDocuments = sqResult.documents ?? {};
          squadSystemPrompt = String(sqResult.documents?.system_prompt_md || "");
        } catch {
          // Squad prompt not available.
        }
      }

      if (!cancelled) {
        setInherited({
          workspaceDocuments,
          workspaceSystemPrompt,
          squadDocuments,
          squadSystemPrompt,
          loading: false,
        });
      }
    };

    void fetchSpecs();

    return () => {
      cancelled = true;
    };
  }, [agent.organization?.workspace_id, agent.organization?.squad_id]);

  const updateField = useCallback(
    (field: keyof EditorState, value: unknown) =>
      dispatch({ type: "updateField", field, value }),
    [dispatch],
  );

  const updateDocument = useCallback(
    (key: string, value: string) =>
      dispatch({ type: "updateDocument", key, value }),
    [dispatch],
  );

  const updateAgentSpecField = useCallback(
    (key: string, value: string) =>
      dispatch({ type: "updateAgentSpecField", key, value }),
    [dispatch],
  );

  const updateSectionJson = useCallback(
    (value: string) =>
      dispatch({ type: "updateSectionJson", value }),
    [dispatch],
  );

  const updateCollectionJson = useCallback(
    (kind: string, value: string) =>
      dispatch({ type: "updateCollectionJson", kind, value }),
    [dispatch],
  );

  const resetDirty = useCallback(
    (section: string) =>
      dispatch({ type: "resetDirty", section }),
    [dispatch],
  );

  const setCompiledPrompt = useCallback(
    (value: string) =>
      dispatch({ type: "setCompiledPrompt", value }),
    [dispatch],
  );

  const setCompiledPromptPayload = useCallback(
    (value: ControlPlaneCompiledPrompt | null) =>
      dispatch({ type: "setCompiledPromptPayload", value }),
    [dispatch],
  );

  const setValidationJson = useCallback(
    (value: string) =>
      dispatch({ type: "setValidationJson", value }),
    [dispatch],
  );

  const discardDraft = useCallback(
    () =>
      dispatch({
        type: "hydrateAgent",
        agent: state.agent,
        compiledPromptPayload: state.compiledPromptPayload,
        executionPolicyPayload: state.executionPolicyPayload,
      }),
    [dispatch, state.agent, state.compiledPromptPayload, state.executionPolicyPayload],
  );

  const refreshCompiledPrompt = useCallback(async () => {
    const payload = await requestJson<ControlPlaneCompiledPrompt>(
      `/api/control-plane/agents/${state.agent.id}/compiled-prompt`,
    );
    dispatch({ type: "setCompiledPromptPayload", value: payload });
    return payload;
  }, [dispatch, state.agent.id]);

  const persistDraft = useCallback(async (options: PersistDraftOptions = {}) => {
    const includeMeta = options.includeMeta ?? state.dirty.meta;
    const includeAgentSpec =
      options.includeAgentSpec ?? (state.dirty.agentSpec || state.dirty.documents);
    const includeCollections = options.includeCollections ?? state.dirty.collections;
    const persisted: string[] = [];
    const agentId = state.agent.id;

    if (includeMeta) {
      const payload = buildAgentMetadataPayload({
        displayName: state.displayName,
        status: state.status,
        storageNamespace: state.storageNamespace,
        workspaceId: state.workspaceId,
        squadId: state.squadId,
        color: state.color,
        colorRgb: state.colorRgb,
        healthPort: state.healthPort,
        healthUrl: state.healthUrl,
        runtimeBaseUrl: state.runtimeBaseUrl,
        appearanceJson: state.appearanceJson,
        runtimeEndpointJson: state.runtimeEndpointJson,
        metadataJson: state.metadataJson,
      });
      await requestJson(`/api/control-plane/agents/${agentId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      dispatch({ type: "resetDirty", section: "meta" });
      persisted.push("meta");
    }

    if (includeAgentSpec) {
      const payload = {
        ...buildAgentSpecPayload({
          missionProfileJson: state.missionProfileJson,
          interactionStyleJson: state.interactionStyleJson,
          operatingInstructionsJson: state.operatingInstructionsJson,
          hardRulesJson: state.hardRulesJson,
          responsePolicyJson: state.responsePolicyJson,
          modelPolicyJson: serializeModelPolicy(
            normalizeModelPolicyForCore(
              parseModelPolicy(state.modelPolicyJson),
              core.providers,
            ),
          ),
          toolPolicyJson: state.toolPolicyJson,
          memoryPolicyJson: state.memoryPolicyJson,
          knowledgePolicyJson: state.knowledgePolicyJson,
          autonomyPolicyJson: state.autonomyPolicyJson,
          resourceAccessPolicyJson: state.resourceAccessPolicyJson,
          voicePolicyJson: state.voicePolicyJson,
          imageAnalysisPolicyJson: state.imageAnalysisPolicyJson,
          memoryExtractionSchemaJson: state.memoryExtractionSchemaJson,
          executionPolicyJson: state.executionPolicyDirty
            ? state.executionPolicyJson
            : undefined,
        }),
        documents: { ...state.documents },
      };
      await requestJson(`/api/control-plane/agents/${agentId}/agent-spec`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      dispatch({ type: "resetDirty", section: "agentSpec" });
      dispatch({ type: "resetDirty", section: "documents" });
      persisted.push("agentSpec");
    }

    if (includeCollections) {
      const collections = [
        {
          field: "Knowledge Assets",
          kind: "knowledge-assets",
          value: state.knowledgeJson,
          existing: state.agent.knowledge_assets ?? [],
        },
        {
          field: "Templates",
          kind: "templates",
          value: state.templatesJson,
          existing: state.agent.templates ?? [],
        },
        {
          field: "Skills",
          kind: "skills",
          value: state.skillsJson,
          existing: state.agent.skills ?? [],
        },
      ] as const;

      for (const collection of collections) {
        const parsed = parseJsonArray(collection.field, collection.value);
        const desiredIds = new Set(
          parsed
            .map((item) => Number(item.id || 0))
            .filter((id) => Number.isInteger(id) && id > 0),
        );

        await Promise.all(
          parsed.map((item) => {
            const id = Number(item.id || 0);
            return requestJson(
              `/api/control-plane/agents/${agentId}/${collection.kind}${id ? `/${id}` : ""}`,
              {
                method: id ? "PUT" : "POST",
                body: JSON.stringify(item),
              },
            );
          }),
        );

        const existingIds = (collection.existing ?? [])
          .map((item) => Number(item.id || 0))
          .filter((id) => Number.isInteger(id) && id > 0);
        const removedIds = existingIds.filter((id) => !desiredIds.has(id));
        await Promise.all(
          removedIds.map((id) =>
            requestJson(`/api/control-plane/agents/${agentId}/${collection.kind}/${id}`, {
              method: "DELETE",
            }),
          ),
        );
      }

      dispatch({ type: "resetDirty", section: "collections" });
      persisted.push("collections");
    }

    if (persisted.length > 0) {
      const freshAgent = await requestJson(`/api/control-plane/agents/${agentId}`);
      let nextCompiledPromptPayload = state.compiledPromptPayload;
      let nextExecutionPolicyPayload = state.executionPolicyPayload;
      if (includeAgentSpec) {
        try {
          nextCompiledPromptPayload = await requestJson<ControlPlaneCompiledPrompt>(
            `/api/control-plane/agents/${agentId}/compiled-prompt`,
          );
        } catch {
          nextCompiledPromptPayload = state.compiledPromptPayload;
        }
        try {
          nextExecutionPolicyPayload = await requestJson<ControlPlaneExecutionPolicyPayload>(
            `/api/control-plane/agents/${agentId}/execution-policy`,
          );
        } catch {
          nextExecutionPolicyPayload = state.executionPolicyPayload;
        }
      }
      dispatch({
        type: "hydrateAgent",
        agent: freshAgent as ControlPlaneAgent,
        compiledPromptPayload: nextCompiledPromptPayload,
        executionPolicyPayload: nextExecutionPolicyPayload,
      });
    }

    return { persisted };
  }, [state, core.providers, dispatch]);

  const value = useMemo<AgentEditorContextValue>(() => ({
    state,
    developerMode,
    setDeveloperMode,
    core,
    workspaces,
    systemSettings,
    inherited,
    dispatch,
    updateField,
    updateDocument,
    updateAgentSpecField,
    updateSectionJson,
    updateCollectionJson,
    resetDirty,
    setCompiledPrompt,
    setCompiledPromptPayload,
    setValidationJson,
    executionPolicyPayload: state.executionPolicyPayload,
    refreshCompiledPrompt,
    discardDraft,
    persistDraft,
  }), [
    state,
    developerMode,
    setDeveloperMode,
    core,
    workspaces,
    systemSettings,
    inherited,
    dispatch,
    updateField,
    updateDocument,
    updateAgentSpecField,
    updateSectionJson,
    updateCollectionJson,
    resetDirty,
    setCompiledPrompt,
    setCompiledPromptPayload,
    setValidationJson,
    refreshCompiledPrompt,
    discardDraft,
    persistDraft,
  ]);

  return React.createElement(AgentEditorContext.Provider, { value }, children);
}

export function useAgentEditor(): AgentEditorContextValue {
  const ctx = useContext(AgentEditorContext);
  if (!ctx) {
    throw new Error("useAgentEditor must be used within a AgentEditorProvider");
  }
  return ctx;
}
