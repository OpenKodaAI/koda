"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { useToast } from "@/hooks/use-toast";
import type {
  ElevenLabsVoiceCatalog,
  GeneralSystemSettings,
  GeneralSystemSettingsCredentialField,
  GeneralSystemSettingsProviderConnection,
  GeneralSystemSettingsVariable,
  KokoroVoiceCatalog,
  ProviderDownloadJob,
  OllamaModelCatalog,
  ProviderLoginSession,
} from "@/lib/control-plane";
import { requestJson } from "@/lib/http-client";
import {
  SECTION_VALUE_KEYS,
  STEP_TO_SECTION,
  type SettingsSectionId,
  cloneGeneralSystemSettings,
  normalizeFallbackOrder,
  removeVariable,
  sanitizeVariableDraft,
  upsertVariable,
} from "@/lib/system-settings-model";
import isEqual from "fast-deep-equal";

type ProviderConnectionDraft = {
  auth_mode: "api_key" | "subscription_login" | "local";
  api_key: string;
  project_id: string;
  base_url: string;
  login_session: ProviderLoginSession | null;
};

type VoiceCatalogCacheEntry = {
  expiresAt: number;
  data: ElevenLabsVoiceCatalog;
};

type OllamaModelCatalogCacheEntry = {
  expiresAt: number;
  data: OllamaModelCatalog;
};

type KokoroVoiceCatalogCacheEntry = {
  expiresAt: number;
  data: KokoroVoiceCatalog;
};

type SystemSettingsContextValue = {
  draft: GeneralSystemSettings;
  dirty: boolean;
  sectionDirty: Record<SettingsSectionId, boolean>;
  isDirty: (sectionId: SettingsSectionId) => boolean;
  discardSection: (sectionId: SettingsSectionId) => void;
  saving: boolean;
  activeSection: SettingsSectionId;
  setActiveSection: (section: string) => void;
  providerOptions: Array<{
    id: string;
    title: string;
    vendor: string;
    category: string;
    commandPresent: boolean;
    supportsApiKey: boolean;
    supportsSubscriptionLogin: boolean;
    supportsLocalConnection: boolean;
    supportedAuthModes: string[];
    loginFlowKind: string;
    requiresProjectId: boolean;
  }>;
  enabledProviders: string[];
  localWarnings: string[];
  editingVariable: GeneralSystemSettingsVariable | null;
  editingVariableOriginalKey: string | null;
  providerConnections: Record<string, GeneralSystemSettingsProviderConnection>;
  providerConnectionDrafts: Record<string, ProviderConnectionDraft>;
  elevenlabsVoiceCatalog: ElevenLabsVoiceCatalog;
  elevenlabsVoicesLoading: boolean;
  kokoroVoiceCatalog: KokoroVoiceCatalog;
  kokoroVoicesLoading: boolean;
  kokoroDownloadJobForVoice: (voiceId: string) => ProviderDownloadJob | null;
  ollamaModelCatalog: OllamaModelCatalog;
  ollamaModelsLoading: boolean;
  setField: <T extends keyof GeneralSystemSettings["values"]>(
    group: T,
    nextGroup: GeneralSystemSettings["values"][T],
  ) => void;
  setProviderConnectionDraft: (
    providerId: string,
    patch: Partial<ProviderConnectionDraft>,
  ) => void;
  connectProviderApiKey: (providerId: string) => Promise<void>;
  startProviderLogin: (providerId: string) => Promise<void>;
  verifyProviderConnection: (providerId: string) => Promise<void>;
  disconnectProviderConnection: (providerId: string) => Promise<void>;
  loadElevenLabsVoices: (language?: string, options?: { force?: boolean }) => Promise<ElevenLabsVoiceCatalog>;
  loadKokoroVoices: (language?: string, options?: { force?: boolean }) => Promise<KokoroVoiceCatalog>;
  downloadKokoroVoice: (voiceId: string) => Promise<void>;
  connectProviderLocal: (providerId: string) => Promise<void>;
  loadOllamaModels: (options?: { force?: boolean }) => Promise<OllamaModelCatalog>;
  isProviderActionPending: (providerId: string, action: "connect" | "verify" | "disconnect") => boolean;
  providerActionStatus: (
    providerId: string,
    action: "connect" | "verify" | "disconnect",
  ) => "idle" | "pending" | "success" | "error";
  moveFallback: (providerId: string, direction: "up" | "down") => void;
  toggleGlobalTool: (toolId: string) => void;
  toggleIntegration: (integrationKey: string) => void;
  setCredentialField: (
    integrationKey: string,
    fieldKey: string,
    updater: (field: GeneralSystemSettingsCredentialField) => GeneralSystemSettingsCredentialField,
  ) => void;
  openNewVariable: () => void;
  openEditVariable: (variable: GeneralSystemSettingsVariable) => void;
  setEditingVariable: (variable: GeneralSystemSettingsVariable | null) => void;
  confirmVariable: () => void;
  handleSave: () => Promise<void>;
  handleDiscard: () => void;
  showToast: ReturnType<typeof useToast>["showToast"];
};

const SystemSettingsContext = createContext<SystemSettingsContextValue | null>(null);

const EMPTY_ELEVENLABS_VOICE_CATALOG: ElevenLabsVoiceCatalog = {
  items: [],
  available_languages: [],
  selected_language: "",
  cached: false,
  provider_connected: false,
};

const EMPTY_OLLAMA_MODEL_CATALOG: OllamaModelCatalog = {
  items: [],
  cached: false,
  provider_connected: false,
  base_url: "",
  auth_mode: "local",
};

const EMPTY_KOKORO_VOICE_CATALOG: KokoroVoiceCatalog = {
  items: [],
  available_languages: [],
  selected_language: "",
  default_language: "pt-br",
  default_voice: "pf_dora",
  default_voice_label: "",
  downloaded_voice_ids: [],
  provider_connected: true,
};

function buildProviderConnectionDrafts(settings: GeneralSystemSettings) {
  const connections = settings.values.provider_connections || {};
  return Object.fromEntries(
    Object.entries(connections).map(([providerId, connection]) => [
      providerId,
      {
        auth_mode: connection.auth_mode,
        api_key: "",
        project_id: connection.project_id || "",
        base_url: connection.base_url || "",
        login_session: null,
      },
    ]),
  ) as Record<string, ProviderConnectionDraft>;
}

function providerActionKey(
  providerId: string,
  action: "connect" | "verify" | "disconnect",
) {
  return `provider:${providerId}:${action}`;
}

export function SystemSettingsProvider({
  settings,
  children,
}: {
  settings: GeneralSystemSettings;
  children: ReactNode;
}) {
  const { tl } = useAppI18n();
  const { showToast } = useToast();
  const { runAction, isPending, getStatus } = useAsyncAction();
  const [draft, setDraft] = useState(() => cloneGeneralSystemSettings(settings));
  const [baseline, setBaseline] = useState<GeneralSystemSettings>(() =>
    cloneGeneralSystemSettings(settings),
  );

  const sectionDirty = useMemo(() => {
    const result: Record<SettingsSectionId, boolean> = {
      general: false, models: false, integrations: false, intelligence: false,
    };
    for (const [sectionId, keys] of Object.entries(SECTION_VALUE_KEYS)) {
      result[sectionId as SettingsSectionId] = keys.some(
        (key) => !isEqual(draft.values[key], baseline.values[key]),
      );
    }
    return result;
  }, [draft, baseline]);

  const dirty = Object.values(sectionDirty).some(Boolean);

  const [storedSection, setStoredSection] = useLocalStorage<string>("ui:settings-step", "general");
  const activeSection: SettingsSectionId =
    (STEP_TO_SECTION[storedSection] as SettingsSectionId) ?? (storedSection as SettingsSectionId) ?? "general";
  const [editingVariable, setEditingVariable] = useState<GeneralSystemSettingsVariable | null>(null);
  const [editingVariableOriginalKey, setEditingVariableOriginalKey] = useState<string | null>(null);
  const [providerConnectionDrafts, setProviderConnectionDrafts] = useState<Record<string, ProviderConnectionDraft>>(
    () => buildProviderConnectionDrafts(settings),
  );
  const [elevenlabsVoiceCatalog, setElevenlabsVoiceCatalog] = useState<ElevenLabsVoiceCatalog>(
    EMPTY_ELEVENLABS_VOICE_CATALOG,
  );
  const [elevenlabsVoicesLoading, setElevenlabsVoicesLoading] = useState(false);
  const [kokoroVoiceCatalog, setKokoroVoiceCatalog] = useState<KokoroVoiceCatalog>(EMPTY_KOKORO_VOICE_CATALOG);
  const [kokoroVoicesLoading, setKokoroVoicesLoading] = useState(false);
  const [kokoroDownloadJobs, setKokoroDownloadJobs] = useState<Record<string, ProviderDownloadJob>>({});
  const [ollamaModelCatalog, setOllamaModelCatalog] = useState<OllamaModelCatalog>(EMPTY_OLLAMA_MODEL_CATALOG);
  const [ollamaModelsLoading, setOllamaModelsLoading] = useState(false);
  const autoVerifySessionsRef = useRef<Record<string, string>>({});
  const elevenlabsVoiceCacheRef = useRef<Record<string, VoiceCatalogCacheEntry>>({});
  const kokoroVoiceCacheRef = useRef<Record<string, KokoroVoiceCatalogCacheEntry>>({});
  const ollamaModelCacheRef = useRef<Record<string, OllamaModelCatalogCacheEntry>>({});

  useEffect(() => {
    const freshClone = cloneGeneralSystemSettings(settings);
    setBaseline(freshClone);
    setDraft(cloneGeneralSystemSettings(settings));
    setProviderConnectionDrafts(buildProviderConnectionDrafts(settings));
    setElevenlabsVoiceCatalog(EMPTY_ELEVENLABS_VOICE_CATALOG);
    setKokoroVoiceCatalog(EMPTY_KOKORO_VOICE_CATALOG);
    setKokoroDownloadJobs({});
    setOllamaModelCatalog(EMPTY_OLLAMA_MODEL_CATALOG);
    elevenlabsVoiceCacheRef.current = {};
    kokoroVoiceCacheRef.current = {};
    ollamaModelCacheRef.current = {};
  }, [settings]);

  const providerOptions = useMemo(
    () =>
      draft.catalogs.providers.map((provider) => ({
        id: String(provider.id),
        title: String(provider.title || provider.id),
        vendor: String(provider.vendor || ""),
        category: String((provider as Record<string, unknown>).category || "general"),
        commandPresent: Boolean(provider.command_present),
        supportsApiKey: Boolean((provider as Record<string, unknown>).supports_api_key),
        supportsSubscriptionLogin: Boolean(
          (provider as Record<string, unknown>).supports_subscription_login,
        ),
        supportsLocalConnection: Boolean(
          (provider as Record<string, unknown>).supports_local_connection,
        ),
        supportedAuthModes: Array.isArray((provider as Record<string, unknown>).supported_auth_modes)
          ? ((provider as Record<string, unknown>).supported_auth_modes as string[])
          : [],
        loginFlowKind: String((provider as Record<string, unknown>).login_flow_kind || ""),
        requiresProjectId: Boolean((provider as Record<string, unknown>).requires_project_id),
      })),
    [draft.catalogs.providers],
  );

  const providerConnections = useMemo(
    () => draft.values.provider_connections || {},
    [draft.values.provider_connections],
  );
  const elevenlabsConnection = providerConnections.elevenlabs;
  const enabledProviders = useMemo(
    () =>
      providerOptions
        .filter((provider) => provider.category === "general")
        .filter((provider) => {
          const managed =
            provider.supportsApiKey ||
            provider.supportsSubscriptionLogin ||
            provider.supportsLocalConnection;
          if (!managed) {
            return provider.commandPresent;
          }
          const connection = providerConnections[provider.id];
          return Boolean(connection?.verified);
        })
        .map((provider) => provider.id),
    [providerConnections, providerOptions],
  );

  const replaceProviderConnection = useCallback((connection: GeneralSystemSettingsProviderConnection) => {
    setDraft((current) => ({
      ...current,
        values: {
          ...current.values,
          provider_connections: {
            ...(current.values.provider_connections || {}),
            [connection.provider_id]: connection,
          },
        },
      }));
  }, []);

  const setProviderConnectionDraft = useCallback(
    (providerId: string, patch: Partial<ProviderConnectionDraft>) => {
      setProviderConnectionDrafts((current) => ({
        ...current,
        [providerId]: {
          ...(current[providerId] || {
            auth_mode: "api_key",
            api_key: "",
            project_id: "",
            base_url: "",
            login_session: null,
          }),
          ...patch,
        },
      }));
    },
    [],
  );

  const loadElevenLabsVoices = useCallback(
    async (language?: string, options?: { force?: boolean }) => {
      const selectedLanguage = String(
        language ?? draft.values.models.elevenlabs_default_language ?? "",
      ).trim().toLowerCase();
      const connected = Boolean(
        elevenlabsConnection?.api_key_present || elevenlabsConnection?.configured || elevenlabsConnection?.verified,
      );
      if (!connected) {
        const emptyState = {
          ...EMPTY_ELEVENLABS_VOICE_CATALOG,
          selected_language: selectedLanguage,
          provider_connected: false,
        };
        setElevenlabsVoiceCatalog(emptyState);
        return emptyState;
      }

      const cacheIdentity = [
        elevenlabsConnection?.api_key_preview || "",
        elevenlabsConnection?.connection_status || "",
        selectedLanguage,
      ].join(":");
      const cached = elevenlabsVoiceCacheRef.current[cacheIdentity];
      const now = Date.now();
      if (!options?.force && cached && cached.expiresAt > now) {
        setElevenlabsVoiceCatalog(cached.data);
        return cached.data;
      }

      setElevenlabsVoicesLoading(true);
      try {
        const query = selectedLanguage ? `?language=${encodeURIComponent(selectedLanguage)}` : "";
        const payload = await requestJson<ElevenLabsVoiceCatalog>(
          `/api/elevenlabs/voices${query}`,
        );
        elevenlabsVoiceCacheRef.current[cacheIdentity] = {
          expiresAt: now + 5 * 60 * 1000,
          data: payload,
        };
        setElevenlabsVoiceCatalog(payload);
        return payload;
      } finally {
        setElevenlabsVoicesLoading(false);
      }
    },
    [draft.values.models.elevenlabs_default_language, elevenlabsConnection],
  );

  const loadKokoroVoices = useCallback(
    async (language?: string, options?: { force?: boolean }) => {
      const selectedLanguage = String(
        language ?? draft.values.models.kokoro_default_language ?? "pt-br",
      ).trim().toLowerCase();
      const cacheIdentity = selectedLanguage || "all";
      const cached = kokoroVoiceCacheRef.current[cacheIdentity];
      const now = Date.now();
      if (!options?.force && cached && cached.expiresAt > now) {
        setKokoroVoiceCatalog(cached.data);
        return cached.data;
      }

      setKokoroVoicesLoading(true);
      try {
        const query = selectedLanguage ? `?language=${encodeURIComponent(selectedLanguage)}` : "";
        const payload = await requestJson<KokoroVoiceCatalog>(
          `/api/control-plane/providers/kokoro/voices${query}`,
        );
        kokoroVoiceCacheRef.current[cacheIdentity] = {
          expiresAt: now + 5 * 60 * 1000,
          data: payload,
        };
        setKokoroVoiceCatalog(payload);
        return payload;
      } finally {
        setKokoroVoicesLoading(false);
      }
    },
    [draft.values.models.kokoro_default_language],
  );

  const loadOllamaModels = useCallback(
    async (options?: { force?: boolean }) => {
      const ollamaConnection = providerConnections.ollama;
      const selectedBaseUrl = String(
        providerConnectionDrafts.ollama?.base_url || ollamaConnection?.base_url || "",
      ).trim();
      const authMode = String(providerConnectionDrafts.ollama?.auth_mode || ollamaConnection?.auth_mode || "local");
      const cacheIdentity = [
        authMode,
        selectedBaseUrl,
        ollamaConnection?.api_key_preview || "",
        ollamaConnection?.connection_status || "",
      ].join(":");
      const cached = ollamaModelCacheRef.current[cacheIdentity];
      const now = Date.now();
      if (!options?.force && cached && cached.expiresAt > now) {
        setOllamaModelCatalog(cached.data);
        return cached.data;
      }

      setOllamaModelsLoading(true);
      try {
        const payload = await requestJson<OllamaModelCatalog>("/api/control-plane/providers/ollama/models");
        ollamaModelCacheRef.current[cacheIdentity] = {
          expiresAt: now + 5 * 60 * 1000,
          data: payload,
        };
        setOllamaModelCatalog(payload);
        return payload;
      } finally {
        setOllamaModelsLoading(false);
      }
    },
    [providerConnectionDrafts.ollama, providerConnections.ollama],
  );

  useEffect(() => {
    const activeJobs = Object.values(kokoroDownloadJobs).filter((job) =>
      ["pending", "running"].includes(String(job.status)),
    );
    if (!activeJobs.length) {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      for (const job of activeJobs) {
        try {
          const refreshed = await requestJson<ProviderDownloadJob>(
            `/api/control-plane/providers/kokoro/downloads/${job.id}`,
          );
          if (cancelled) return;
          setKokoroDownloadJobs((current) => ({ ...current, [refreshed.asset_id]: refreshed }));
          if (refreshed.status === "completed") {
            kokoroVoiceCacheRef.current = {};
            await loadKokoroVoices(
              draft.values.models.kokoro_default_language || refreshed.language_id || "pt-br",
              { force: true },
            );
          }
        } catch {
          // Keep last visible state until the user retries.
        }
      }
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [draft.values.models.kokoro_default_language, kokoroDownloadJobs, loadKokoroVoices]);

  const verifyProviderConnectionSilently = useCallback(
    async (providerId: string) => {
      const payload = await requestJson<{
        connection: GeneralSystemSettingsProviderConnection;
        verification: Record<string, unknown>;
      }>(`/api/control-plane/providers/${providerId}/connection/verify`, {
        method: "POST",
      });
      replaceProviderConnection(payload.connection);
      setProviderConnectionDraft(providerId, {
        project_id: payload.connection.project_id || "",
        base_url: payload.connection.base_url || "",
        login_session: null,
      });
      return payload;
    },
    [replaceProviderConnection, setProviderConnectionDraft],
  );

  useEffect(() => {
    const activeSessions = Object.entries(providerConnectionDrafts)
      .map(([providerId, draftConnection]) => ({
        providerId,
        session: draftConnection.login_session,
      }))
      .filter((entry) => entry.session) as Array<{
      providerId: string;
      session: ProviderLoginSession;
    }>;

    if (activeSessions.length === 0) {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      for (const { providerId, session } of activeSessions) {
        try {
          const refreshed = await requestJson<ProviderLoginSession>(
            `/api/control-plane/providers/${providerId}/connection/login/${session.session_id}`,
          );
          if (cancelled) return;
          setProviderConnectionDraft(providerId, { login_session: refreshed });
          if (
            refreshed.status === "completed" &&
            autoVerifySessionsRef.current[providerId] !== refreshed.session_id
          ) {
            autoVerifySessionsRef.current[providerId] = refreshed.session_id;
            try {
              await verifyProviderConnectionSilently(providerId);
            } catch {
              // Keep the completed login session visible so the user still has context.
            }
          }
        } catch {
          // Keep the last visible state until the user retries or verifies manually.
        }
      }
    };

    void poll();
    const interval = window.setInterval(() => {
      void poll();
    }, 2500);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [providerConnectionDrafts, setProviderConnectionDraft, verifyProviderConnectionSilently]);

  const localWarnings = useMemo(() => {
    const warnings = [...draft.review.warnings];
    const functionalDefaults = draft.values.models.functional_defaults || {};
    const functionalCatalog = draft.catalogs.functional_model_catalog || {};
    const autonomyPolicy = (draft.values.memory_and_knowledge.autonomy_policy || {}) as Record<string, unknown>;
    const knowledgePolicy = (draft.values.memory_and_knowledge.knowledge_policy || {}) as Record<string, unknown>;
    const memoryPolicy = (draft.values.memory_and_knowledge.memory_policy || {}) as Record<string, unknown>;
    const memoryProfile = (
      memoryPolicy.profile && typeof memoryPolicy.profile === "object" && !Array.isArray(memoryPolicy.profile)
        ? memoryPolicy.profile
        : {}
    ) as Record<string, unknown>;
    const promotionPolicy = (
      memoryProfile.promotion_policy &&
      typeof memoryProfile.promotion_policy === "object" &&
      !Array.isArray(memoryProfile.promotion_policy)
        ? memoryProfile.promotion_policy
        : {}
    ) as Record<string, unknown>;
    const defaultAutonomyTier = String(autonomyPolicy.default_autonomy_tier || "t1").toLowerCase();
    const allowedKnowledgeLayers = Array.isArray(knowledgePolicy.allowed_layers)
      ? knowledgePolicy.allowed_layers.map((item) => String(item).toLowerCase())
      : [];
    if (enabledProviders.length > 0 && !enabledProviders.includes(draft.values.models.default_provider)) {
      warnings.push(tl("O provider padrão precisa estar dentro da lista de providers habilitados."));
    }
    if (enabledProviders.length > 0 && draft.values.models.fallback_order.length === 0) {
      warnings.push(tl("Defina a ordem de fallback para os providers habilitados."));
    }
    for (const providerId of enabledProviders) {
      const connection = providerConnections[providerId];
      if (connection && !connection.verified) {
        warnings.push(
          tl("{{provider}} precisa estar conectado e verificado para ficar habilitado.", {
            provider: connection.title || providerId,
          }),
        );
      }
    }
    for (const [integrationKey, enabled] of Object.entries(draft.values.resources.integrations)) {
      if (!enabled) continue;
      const integrationName = integrationKey.replace("_enabled", "");
      const credentialBlock = draft.values.integration_credentials[integrationName];
      if (!credentialBlock) continue;
      const missingFields = credentialBlock.fields
        .filter((field) => field.required && !(field.value || field.value_present))
        .map((field) => field.label);
      if (missingFields.length > 0) {
        warnings.push(
          tl("{{title}} está habilitado, mas faltam credenciais obrigatórias: {{fields}}.", {
            title: credentialBlock.title,
            fields: missingFields.join(", "),
          }),
        );
      }
    }
    for (const [functionId, selection] of Object.entries(functionalDefaults)) {
      const option = (functionalCatalog[functionId] || []).find(
        (item) =>
          item.provider_id === selection.provider_id && item.model_id === selection.model_id,
      );
      if (!option) {
        warnings.push(
          tl("O default de {{functionId}} aponta para um modelo que não existe mais no catálogo.", {
            functionId,
          }),
        );
        continue;
      }
      const connection = providerConnections[selection.provider_id];
      const managedProvider =
        providerOptions.find((provider) => provider.id === selection.provider_id)?.supportsApiKey ||
        providerOptions.find((provider) => provider.id === selection.provider_id)?.supportsSubscriptionLogin;
      if (managedProvider && connection && !connection.verified) {
        warnings.push(
          tl("{{provider}} precisa estar verificado para ser usado como default de {{functionId}}.", {
            provider: option.provider_title,
            functionId,
          }),
        );
      }
      if (
        functionId === "transcription" &&
        selection.provider_id === "codex" &&
        (!connection?.api_key_present || connection?.auth_mode !== "api_key")
      ) {
        warnings.push(tl("OpenAI Whisper via API exige conexão do provider OpenAI em modo API Key."));
      }
    }
    if (["t1", "t2"].includes(defaultAutonomyTier) && !draft.values.memory_and_knowledge.knowledge_enabled) {
      warnings.push(tl("Autonomia acima de T0 sem RAG habilitado reduz muito a confiabilidade operacional do agente."));
    }
    if (
      defaultAutonomyTier === "t2" &&
      (!allowedKnowledgeLayers.includes("canonical_policy") ||
        !allowedKnowledgeLayers.includes("approved_runbook"))
    ) {
      warnings.push(tl("T2 deveria manter conhecimento canônico e runbooks aprovados entre as camadas permitidas."));
    }
    if (
      defaultAutonomyTier === "t2" &&
      knowledgePolicy.require_owner_provenance !== true
    ) {
      warnings.push(tl("T2 sem owner provenance enfraquece o grounding para ações sensíveis."));
    }
    if (
      memoryPolicy.procedural_enabled === true &&
      promotionPolicy.observed_pattern_requires_review === false
    ) {
      warnings.push(tl("Aprendizado procedural sem revisão antes da promoção aumenta o risco de drift comportamental."));
    }
    return Array.from(new Set(warnings));
  }, [draft, enabledProviders, providerConnections, providerOptions, tl]);

  const isDirty = useCallback(
    (sectionId: SettingsSectionId) => sectionDirty[sectionId],
    [sectionDirty],
  );

  const discardSection = useCallback(
    (sectionId: SettingsSectionId) => {
      const keys = SECTION_VALUE_KEYS[sectionId];
      setDraft((prev) => {
        const nextValues = { ...prev.values };
        for (const key of keys) {
          (nextValues as Record<string, unknown>)[key] = structuredClone(baseline.values[key]);
        }
        return { ...prev, values: nextValues };
      });
    },
    [baseline],
  );

  function setField<T extends keyof GeneralSystemSettings["values"]>(
    group: T,
    nextGroup: GeneralSystemSettings["values"][T],
  ) {
    setDraft((prev) => ({
      ...prev,
      values: { ...prev.values, [group]: nextGroup },
    }));
  }

  function moveFallback(providerId: string, direction: "up" | "down") {
    const list = [...draft.values.models.fallback_order];
    const index = list.indexOf(providerId);
    if (index === -1) return;
    const swapWith = direction === "up" ? index - 1 : index + 1;
    if (swapWith < 0 || swapWith >= list.length) return;
    [list[index], list[swapWith]] = [list[swapWith], list[index]];
    setField("models", {
      ...draft.values.models,
      fallback_order: normalizeFallbackOrder(
        enabledProviders,
        list,
        draft.values.models.default_provider,
      ),
    });
  }

  function toggleGlobalTool(toolId: string) {
    const currentTools = draft.values.resources.global_tools;
    const nextTools = currentTools.includes(toolId)
      ? currentTools.filter((item) => item !== toolId)
      : [...currentTools, toolId];
    setField("resources", {
      ...draft.values.resources,
      global_tools: nextTools,
    });
  }

  function toggleIntegration(integrationKey: string) {
    setField("resources", {
      ...draft.values.resources,
      integrations: {
        ...draft.values.resources.integrations,
        [integrationKey]: !draft.values.resources.integrations[integrationKey],
      },
    });
  }

  function setCredentialField(
    integrationKey: string,
    fieldKey: string,
    updater: (field: GeneralSystemSettingsCredentialField) => GeneralSystemSettingsCredentialField,
  ) {
    const integration = draft.values.integration_credentials[integrationKey];
    if (!integration) return;
    const nextFields = integration.fields.map((field) =>
      field.key === fieldKey ? updater(field) : field,
    );
    setField("integration_credentials", {
      ...draft.values.integration_credentials,
      [integrationKey]: {
        ...integration,
        fields: nextFields,
      },
    });
  }

  function openNewVariable() {
    setEditingVariableOriginalKey(null);
    setEditingVariable(
      sanitizeVariableDraft({
        key: "",
        type: "text",
        scope: "system_only",
        description: "",
        value: "",
        preview: "",
        value_present: false,
      }),
    );
  }

  function openEditVariable(variable: GeneralSystemSettingsVariable) {
    setEditingVariableOriginalKey(variable.key);
    setEditingVariable(sanitizeVariableDraft(variable));
  }

  function confirmVariable() {
    if (!editingVariable) return;
    const sanitized = sanitizeVariableDraft(editingVariable);
    if (!sanitized.key) {
      showToast(tl("Informe o nome da variável."), "warning");
      return;
    }
    if (sanitized.type === "text" && !sanitized.value.trim()) {
      showToast(tl("Informe um valor para a variável."), "warning");
      return;
    }
    if (sanitized.type === "secret" && !sanitized.value.trim() && !sanitized.value_present && !sanitized.clear) {
      showToast(tl("Informe um valor inicial para o segredo."), "warning");
      return;
    }
    const baseVariables =
      editingVariableOriginalKey && editingVariableOriginalKey !== sanitized.key
        ? removeVariable(draft.values.variables, editingVariableOriginalKey)
        : draft.values.variables;
    setField("variables", upsertVariable(baseVariables, sanitized));
    setEditingVariableOriginalKey(null);
    setEditingVariable(null);
  }

  const connectProviderApiKey = useCallback(
    async (providerId: string) => {
      const connectionDraft = providerConnectionDrafts[providerId];
      await runAction(
        providerActionKey(providerId, "connect"),
        async () => {
          await requestJson<{ connection: GeneralSystemSettingsProviderConnection } | GeneralSystemSettingsProviderConnection>(
            `/api/control-plane/providers/${providerId}/connection/api-key`,
            {
              method: "PUT",
              body: JSON.stringify({
                api_key: connectionDraft?.api_key || "",
                project_id: connectionDraft?.project_id || "",
                base_url: connectionDraft?.base_url || "",
              }),
            },
          );
          const verification = await verifyProviderConnectionSilently(providerId);
          if (!Boolean(verification.verification?.verified)) {
            throw new Error(
              String(
                verification.verification?.last_error || tl("Nao foi possivel validar a API Key deste provider."),
              ),
            );
          }
          return verification;
        },
        {
          successMessage: tl("Provider conectado com sucesso."),
          errorMessage: tl("Nao foi possivel conectar o provider via API Key."),
          onSuccess: (payload) => {
            const connection = payload.connection;
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: "api_key",
              api_key: "",
              project_id: connection.project_id || connectionDraft?.project_id || "",
              base_url: connection.base_url || connectionDraft?.base_url || "",
              login_session: null,
            });
            if (providerId === "elevenlabs") {
              elevenlabsVoiceCacheRef.current = {};
              void loadElevenLabsVoices(draft.values.models.elevenlabs_default_language, { force: true });
            } else if (providerId === "ollama") {
              ollamaModelCacheRef.current = {};
              void loadOllamaModels({ force: true });
            }
          },
        },
      );
    },
    [
      draft.values.models.elevenlabs_default_language,
      loadElevenLabsVoices,
      loadOllamaModels,
      providerConnectionDrafts,
      replaceProviderConnection,
      runAction,
      setProviderConnectionDraft,
      verifyProviderConnectionSilently,
      tl,
    ],
  );

  const connectProviderLocal = useCallback(
    async (providerId: string) => {
      const connectionDraft = providerConnectionDrafts[providerId];
      await runAction(
        providerActionKey(providerId, "connect"),
        async () => {
          await requestJson<{ connection: GeneralSystemSettingsProviderConnection } | GeneralSystemSettingsProviderConnection>(
            `/api/control-plane/providers/${providerId}/connection/local`,
            {
              method: "PUT",
              body: JSON.stringify({
                base_url: connectionDraft?.base_url || "",
              }),
            },
          );
          const verification = await verifyProviderConnectionSilently(providerId);
          if (!Boolean(verification.verification?.verified)) {
            throw new Error(
              String(
                verification.verification?.last_error || tl("Nao foi possivel validar a conexao local deste provider."),
              ),
            );
          }
          return verification;
        },
        {
          successMessage: tl("Provider local conectado com sucesso."),
          errorMessage: tl("Nao foi possivel conectar o provider local."),
          onSuccess: (payload) => {
            const connection = payload.connection;
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: "local",
              api_key: "",
              project_id: connection.project_id || "",
              base_url: connection.base_url || connectionDraft?.base_url || "",
              login_session: null,
            });
            if (providerId === "ollama") {
              ollamaModelCacheRef.current = {};
              void loadOllamaModels({ force: true });
            }
          },
        },
      );
    },
    [
      loadOllamaModels,
      providerConnectionDrafts,
      replaceProviderConnection,
      runAction,
      setProviderConnectionDraft,
      verifyProviderConnectionSilently,
      tl,
    ],
  );

  const startProviderLogin = useCallback(
    async (providerId: string) => {
      const connectionDraft = providerConnectionDrafts[providerId];
      await runAction(
        providerActionKey(providerId, "connect"),
        async () =>
          requestJson<{
            connection: GeneralSystemSettingsProviderConnection;
            login_session: ProviderLoginSession;
          }>(`/api/control-plane/providers/${providerId}/connection/login/start`, {
            method: "POST",
            body: JSON.stringify({
              project_id: connectionDraft?.project_id || "",
            }),
          }),
        {
          successMessage: tl("Fluxo oficial de login iniciado."),
          errorMessage: tl("Nao foi possivel iniciar o login oficial do provider."),
          onSuccess: ({ connection, login_session }) => {
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: "subscription_login",
              api_key: "",
              project_id: connection.project_id || connectionDraft?.project_id || "",
              login_session,
            });
            if (login_session.auth_url) {
              window.open(login_session.auth_url, "_blank", "noopener,noreferrer");
            }
          },
        },
      );
    },
    [providerConnectionDrafts, replaceProviderConnection, runAction, setProviderConnectionDraft, tl],
  );

  const verifyProviderConnection = useCallback(
    async (providerId: string) => {
      await runAction(
        providerActionKey(providerId, "verify"),
        async () => verifyProviderConnectionSilently(providerId),
        {
          successMessage: tl("Conexão verificada com sucesso."),
          errorMessage: tl("Nao foi possivel verificar a conexao do provider."),
          onSuccess: (payload) => {
            const connection = payload.connection;
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: connection.auth_mode,
              project_id: connection.project_id || "",
              base_url: connection.base_url || "",
              login_session: null,
            });
          },
        },
      );
    },
    [replaceProviderConnection, runAction, setProviderConnectionDraft, tl, verifyProviderConnectionSilently],
  );

  const disconnectProviderConnection = useCallback(
    async (providerId: string) => {
      await runAction(
        providerActionKey(providerId, "disconnect"),
        async () =>
          requestJson<{ connection: GeneralSystemSettingsProviderConnection }>(
            `/api/control-plane/providers/${providerId}/connection/disconnect`,
            {
              method: "POST",
            },
          ),
        {
          successMessage: tl("Provider desconectado."),
          errorMessage: tl("Nao foi possivel desconectar o provider."),
          onSuccess: ({ connection }) => {
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: providerId === "ollama" ? "local" : "api_key",
              api_key: "",
              project_id: connection.project_id || "",
              base_url: connection.base_url || "",
              login_session: null,
            });
            if (providerId === "elevenlabs") {
              elevenlabsVoiceCacheRef.current = {};
              setElevenlabsVoiceCatalog({
                ...EMPTY_ELEVENLABS_VOICE_CATALOG,
                selected_language: draft.values.models.elevenlabs_default_language,
                provider_connected: false,
              });
            } else if (providerId === "ollama") {
              ollamaModelCacheRef.current = {};
              setOllamaModelCatalog({
                ...EMPTY_OLLAMA_MODEL_CATALOG,
                base_url: connection.base_url || "",
                auth_mode: "local",
              });
            }
          },
        },
      );
    },
    [
      draft.values.models.elevenlabs_default_language,
      setOllamaModelCatalog,
      replaceProviderConnection,
      runAction,
      setProviderConnectionDraft,
      tl,
    ],
  );

  const downloadKokoroVoice = useCallback(
    async (voiceId: string) => {
      await runAction(
        `provider:kokoro:download:${voiceId}`,
        async () =>
          requestJson<ProviderDownloadJob>(`/api/control-plane/providers/kokoro/voices/${voiceId}/download`, {
            method: "POST",
          }),
        {
          successMessage: tl("Download da voz iniciado."),
          errorMessage: tl("Nao foi possivel iniciar o download da voz."),
          onSuccess: (job) => {
            setKokoroDownloadJobs((current) => ({ ...current, [job.asset_id]: job }));
          },
        },
      );
    },
    [runAction, tl],
  );

  async function handleSave() {
    await runAction(
      "save-general-settings",
      async () => {
        const generalDefault = draft.values.models.functional_defaults?.general;
        const defaultProvider = generalDefault?.provider_id || draft.values.models.default_provider;
        const payload = {
          account: draft.values.account,
          models: {
            ...draft.values.models,
            providers_enabled: enabledProviders,
            default_provider: defaultProvider,
            fallback_order: normalizeFallbackOrder(
              enabledProviders,
              draft.values.models.fallback_order,
              defaultProvider,
            ),
          },
          resources: draft.values.resources,
          memory_and_knowledge: draft.values.memory_and_knowledge,
          variables: draft.values.variables,
          integration_credentials: draft.values.integration_credentials,
        };
        const refreshed = await requestJson<GeneralSystemSettings>("/api/control-plane/system-settings/general", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        const freshState = cloneGeneralSystemSettings(refreshed);
        setBaseline(freshState);
        setDraft(cloneGeneralSystemSettings(refreshed));
        setProviderConnectionDrafts(buildProviderConnectionDrafts(refreshed));
        setElevenlabsVoiceCatalog(EMPTY_ELEVENLABS_VOICE_CATALOG);
        setKokoroVoiceCatalog(EMPTY_KOKORO_VOICE_CATALOG);
        setKokoroDownloadJobs({});
        setOllamaModelCatalog(EMPTY_OLLAMA_MODEL_CATALOG);
        elevenlabsVoiceCacheRef.current = {};
        kokoroVoiceCacheRef.current = {};
        ollamaModelCacheRef.current = {};
        return refreshed;
      },
      {
        successMessage: tl("Configuracoes gerais salvas com sucesso."),
        errorMessage: tl("Nao foi possivel salvar as configuracoes gerais."),
      },
    );
  }

  function handleDiscard() {
    setDraft(cloneGeneralSystemSettings(baseline));
    setProviderConnectionDrafts(buildProviderConnectionDrafts(baseline));
    setElevenlabsVoiceCatalog(EMPTY_ELEVENLABS_VOICE_CATALOG);
    setKokoroVoiceCatalog(EMPTY_KOKORO_VOICE_CATALOG);
    setKokoroDownloadJobs({});
    setOllamaModelCatalog(EMPTY_OLLAMA_MODEL_CATALOG);
    elevenlabsVoiceCacheRef.current = {};
    kokoroVoiceCacheRef.current = {};
    ollamaModelCacheRef.current = {};
  }

  const value: SystemSettingsContextValue = {
    draft,
    dirty,
    sectionDirty,
    isDirty,
    discardSection,
    saving: isPending("save-general-settings"),
    activeSection,
    setActiveSection: setStoredSection,
    providerOptions,
    enabledProviders,
    localWarnings,
    editingVariable,
    editingVariableOriginalKey,
    providerConnections,
    providerConnectionDrafts,
    elevenlabsVoiceCatalog,
    elevenlabsVoicesLoading,
    kokoroVoiceCatalog,
    kokoroVoicesLoading,
    kokoroDownloadJobForVoice: (voiceId) => kokoroDownloadJobs[String(voiceId).trim().toLowerCase()] || null,
    ollamaModelCatalog,
    ollamaModelsLoading,
    setField,
    setProviderConnectionDraft,
    connectProviderApiKey,
    connectProviderLocal,
    startProviderLogin,
    verifyProviderConnection,
    disconnectProviderConnection,
    loadElevenLabsVoices,
    loadKokoroVoices,
    downloadKokoroVoice,
    loadOllamaModels,
    isProviderActionPending: (providerId, action) => isPending(providerActionKey(providerId, action)),
    providerActionStatus: (providerId, action) => getStatus(providerActionKey(providerId, action)),
    moveFallback,
    toggleGlobalTool,
    toggleIntegration,
    setCredentialField,
    openNewVariable,
    openEditVariable,
    setEditingVariable,
    confirmVariable,
    handleSave,
    handleDiscard,
    showToast,
  };

  return <SystemSettingsContext.Provider value={value}>{children}</SystemSettingsContext.Provider>;
}

export function useSystemSettings() {
  const ctx = useContext(SystemSettingsContext);
  if (!ctx) throw new Error("useSystemSettings must be used within SystemSettingsProvider");
  return ctx;
}
