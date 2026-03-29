"use client";

import React, {
  createContext,
  useContext,
  useReducer,
  useEffect,
  type ReactNode,
} from "react";
import { useLocalStorage } from "@/hooks/use-local-storage";
import {
  buildAgentSpecPayload,
  buildBotMetadataPayload,
  parseJsonArray,
  prettyJson,
} from "@/lib/control-plane-editor";
import {
  normalizeModelPolicyForCore,
  parseModelPolicy,
  serializeModelPolicy,
} from "@/lib/policy-serializers";
import type {
  ControlPlaneBot,
  ControlPlaneCompiledPrompt,
  ControlPlaneCoreCapabilities,
  ControlPlaneCorePolicies,
  ControlPlaneCoreProviders,
  ControlPlaneSystemSettings,
  ControlPlaneCoreTools,
  ControlPlaneWorkspaceTree,
} from "@/lib/control-plane";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export type EditorState = {
  bot: ControlPlaneBot;
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
  resourceAccessPolicyJson: string;
  voicePolicyJson: string;
  imageAnalysisPolicyJson: string;
  memoryExtractionSchemaJson: string;
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
  | { type: "hydrateBot"; bot: ControlPlaneBot; compiledPromptPayload?: ControlPlaneCompiledPrompt | null };

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

    case "hydrateBot": {
      const nextState = buildInitialState(action.bot, action.compiledPromptPayload);
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
  bot: ControlPlaneBot,
  payload?: ControlPlaneCompiledPrompt | null,
): ControlPlaneCompiledPrompt | null {
  if (payload) {
    return payload;
  }

  if (!bot.compiled_prompt && !bot.validation?.compiled_prompt) {
    return null;
  }

  return {
    bot_id: bot.id,
    compiled_prompt: bot.compiled_prompt || bot.validation?.compiled_prompt || "",
    documents: bot.validation?.documents ?? {},
    document_sources: bot.validation?.document_sources,
    sections_present: bot.validation?.sections_present,
    document_lengths: bot.validation?.document_lengths,
    prompt_preview: bot.validation?.prompt_preview,
    agent_contract_prompt_preview:
      bot.validation?.agent_contract_prompt_preview ?? bot.validation?.bot_contract_prompt_preview,
    bot_contract_prompt_preview:
      bot.validation?.agent_contract_prompt_preview ?? bot.validation?.bot_contract_prompt_preview,
    runtime_prompt_preview: bot.validation?.runtime_prompt_preview,
  };
}

function buildInitialState(
  bot: ControlPlaneBot,
  compiledPromptPayload?: ControlPlaneCompiledPrompt | null,
): EditorState {
  const rt = bot.runtime_endpoint as Record<string, unknown>;
  const spec = bot.agent_spec as Record<string, unknown>;
  const normalizedCompiledPromptPayload = normalizeCompiledPromptPayload(bot, compiledPromptPayload);

  return {
    bot,
    // Meta
    displayName: bot.display_name,
    status: bot.status,
    storageNamespace: bot.storage_namespace,
    workspaceId: bot.organization?.workspace_id ?? "",
    squadId: bot.organization?.squad_id ?? "",
    color: bot.appearance.color ?? "",
    colorRgb: bot.appearance.color_rgb ?? "",
    healthPort: String(rt.health_port ?? ""),
    healthUrl: String(rt.health_url ?? ""),
    runtimeBaseUrl: String(rt.runtime_base_url ?? ""),
    appearanceJson: prettyJson(bot.appearance),
    runtimeEndpointJson: prettyJson(bot.runtime_endpoint),
    metadataJson: prettyJson(bot.metadata),
    // Documents
    documents: { ...bot.documents },
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
    resourceAccessPolicyJson: prettyJson(spec.resource_access_policy ?? {}),
    voicePolicyJson: prettyJson(spec.voice_policy ?? {}),
    imageAnalysisPolicyJson: prettyJson(spec.image_analysis_policy ?? {}),
    memoryExtractionSchemaJson: prettyJson(spec.memory_extraction_schema ?? {}),
    // Sections
    sectionsJson: prettyJson(bot.sections),
    // Collections
    knowledgeJson: prettyJson(bot.knowledge_assets),
    templatesJson: prettyJson(bot.templates),
    skillsJson: prettyJson(bot.skills),
    // Publishing
    compiledPrompt: normalizedCompiledPromptPayload?.compiled_prompt || bot.compiled_prompt,
    compiledPromptPayload: normalizedCompiledPromptPayload,
    validationJson: prettyJson(bot.validation),
    // Secrets
    secretKey: "",
    secretValue: "",
    secretScope: "",
    // Clone
    cloneId: "",
    cloneDisplayName: "",
    // Governance
    knowledgeCandidatesJson: prettyJson(bot.knowledge_candidates ?? []),
    runbooksJson: prettyJson(bot.runbooks ?? []),
    candidateActionId: "",
    runbookActionId: "",
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

type BotEditorContextValue = {
  state: EditorState;
  developerMode: boolean;
  setDeveloperMode: (value: boolean | ((prev: boolean) => boolean)) => void;
  core: {
    tools: ControlPlaneCoreTools;
    providers: ControlPlaneCoreProviders;
    policies: ControlPlaneCorePolicies;
    capabilities: ControlPlaneCoreCapabilities;
  };
  workspaces: ControlPlaneWorkspaceTree;
  systemSettings: ControlPlaneSystemSettings;
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
  refreshCompiledPrompt: () => Promise<ControlPlaneCompiledPrompt>;
  discardDraft: () => void;
  persistDraft: (options?: PersistDraftOptions) => Promise<{ persisted: string[] }>;
};

const BotEditorContext = createContext<BotEditorContextValue | null>(null);

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

export function BotEditorProvider({
  bot,
  compiledPromptPayload,
  core,
  workspaces,
  systemSettings,
  children,
}: {
  bot: ControlPlaneBot;
  compiledPromptPayload?: ControlPlaneCompiledPrompt | null;
  core: {
    tools: ControlPlaneCoreTools;
    providers: ControlPlaneCoreProviders;
    policies: ControlPlaneCorePolicies;
    capabilities: ControlPlaneCoreCapabilities;
  };
  workspaces: ControlPlaneWorkspaceTree;
  systemSettings: ControlPlaneSystemSettings;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(
    reducer,
    { bot, compiledPromptPayload },
    ({ bot: initialBot, compiledPromptPayload: initialCompiledPromptPayload }) =>
      buildInitialState(initialBot, initialCompiledPromptPayload),
  );
  const [developerMode, setDeveloperMode] = useLocalStorage<boolean>(
    "ui:bot-editor:developer-mode",
    false,
  );

  useEffect(() => {
    dispatch({ type: "hydrateBot", bot, compiledPromptPayload });
  }, [bot, compiledPromptPayload]);

  const updateField = (field: keyof EditorState, value: unknown) =>
    dispatch({ type: "updateField", field, value });

  const updateDocument = (key: string, value: string) =>
    dispatch({ type: "updateDocument", key, value });

  const updateAgentSpecField = (key: string, value: string) =>
    dispatch({ type: "updateAgentSpecField", key, value });

  const updateSectionJson = (value: string) =>
    dispatch({ type: "updateSectionJson", value });

  const updateCollectionJson = (kind: string, value: string) =>
    dispatch({ type: "updateCollectionJson", kind, value });

  const resetDirty = (section: string) =>
    dispatch({ type: "resetDirty", section });

  const setCompiledPrompt = (value: string) =>
    dispatch({ type: "setCompiledPrompt", value });

  const setCompiledPromptPayload = (value: ControlPlaneCompiledPrompt | null) =>
    dispatch({ type: "setCompiledPromptPayload", value });

  const setValidationJson = (value: string) =>
    dispatch({ type: "setValidationJson", value });

  const discardDraft = () =>
    dispatch({
      type: "hydrateBot",
      bot: state.bot,
      compiledPromptPayload: state.compiledPromptPayload,
    });

  const refreshCompiledPrompt = async () => {
    const payload = await requestJson<ControlPlaneCompiledPrompt>(
      `/api/control-plane/agents/${state.bot.id}/compiled-prompt`,
    );
    dispatch({ type: "setCompiledPromptPayload", value: payload });
    return payload;
  };

  const persistDraft = async (options: PersistDraftOptions = {}) => {
    const includeMeta = options.includeMeta ?? state.dirty.meta;
    const includeAgentSpec =
      options.includeAgentSpec ?? (state.dirty.agentSpec || state.dirty.documents);
    const includeCollections = options.includeCollections ?? state.dirty.collections;
    const persisted: string[] = [];
    const botId = state.bot.id;

    if (includeMeta) {
      const payload = buildBotMetadataPayload({
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
      await requestJson(`/api/control-plane/agents/${botId}`, {
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
        }),
        documents: { ...state.documents },
      };
      await requestJson(`/api/control-plane/agents/${botId}/agent-spec`, {
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
          existing: state.bot.knowledge_assets ?? [],
        },
        {
          field: "Templates",
          kind: "templates",
          value: state.templatesJson,
          existing: state.bot.templates ?? [],
        },
        {
          field: "Skills",
          kind: "skills",
          value: state.skillsJson,
          existing: state.bot.skills ?? [],
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
              `/api/control-plane/agents/${botId}/${collection.kind}${id ? `/${id}` : ""}`,
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
            requestJson(`/api/control-plane/agents/${botId}/${collection.kind}/${id}`, {
              method: "DELETE",
            }),
          ),
        );
      }

      dispatch({ type: "resetDirty", section: "collections" });
      persisted.push("collections");
    }

    if (persisted.length > 0) {
      const freshBot = await requestJson(`/api/control-plane/agents/${botId}`);
      let nextCompiledPromptPayload = state.compiledPromptPayload;
      if (includeAgentSpec) {
        try {
          nextCompiledPromptPayload = await requestJson<ControlPlaneCompiledPrompt>(
            `/api/control-plane/agents/${botId}/compiled-prompt`,
          );
        } catch {
          nextCompiledPromptPayload = state.compiledPromptPayload;
        }
      }
      dispatch({
        type: "hydrateBot",
        bot: freshBot as ControlPlaneBot,
        compiledPromptPayload: nextCompiledPromptPayload,
      });
    }

    return { persisted };
  };

  const value: BotEditorContextValue = {
    state,
    developerMode,
    setDeveloperMode,
    core,
    workspaces,
    systemSettings,
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
  };

  return React.createElement(BotEditorContext.Provider, { value }, children);
}

export function useBotEditor(): BotEditorContextValue {
  const ctx = useContext(BotEditorContext);
  if (!ctx) {
    throw new Error("useBotEditor must be used within a BotEditorProvider");
  }
  return ctx;
}
