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
  ControlPlaneAgentConnection,
  ControlPlaneCoreIntegration,
  ControlPlaneCoreIntegrationConnection,
  ControlPlaneCoreIntegrations,
  ElevenLabsVoiceCatalog,
  GeneralSystemSettingsCatalogProvider,
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
  groupErrorsBySection,
  sectionForField,
  validatePayloadClientSide,
  type SystemSettingsFieldError,
} from "@/lib/system-settings-schema";
import {
  DEFAULT_SETTINGS_SECTION_ID,
  SECTION_VALUE_KEYS,
  STEP_TO_SECTION,
  type SettingsSectionId,
  cloneGeneralSystemSettings,
  isSettingsSectionId,
  normalizeFallbackOrder,
  removeVariable,
  sanitizeVariableDraft,
  upsertVariable,
} from "@/lib/system-settings-model";
import isEqual from "fast-deep-equal";

const EMPTY_SECTION_ERRORS: Record<SettingsSectionId, SystemSettingsFieldError[]> = {
  general: [],
  models: [],
  integrations: [],
  intelligence: [],
  scheduler: [],
  variables: [],
};

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

type IntegrationAction = "connect" | "verify" | "disconnect" | "enable" | "disable";

type IntegrationVerificationResponse = {
  connection: ControlPlaneCoreIntegrationConnection;
  verification: Record<string, unknown>;
};

type IntegrationVerificationCacheEntry = {
  fingerprint: string;
  expiresAt: number;
  connection: ControlPlaneCoreIntegrationConnection;
};

type SystemSettingsContextValue = {
  draft: GeneralSystemSettings;
  dirty: boolean;
  sectionDirty: Record<SettingsSectionId, boolean>;
  isDirty: (sectionId: SettingsSectionId) => boolean;
  discardSection: (sectionId: SettingsSectionId) => void;
  sectionErrors: Record<SettingsSectionId, SystemSettingsFieldError[]>;
  clearSectionErrors: (sectionId?: SettingsSectionId) => void;
  saving: boolean;
  saveStatus: "idle" | "pending" | "success" | "error";
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
    connectionManaged: boolean;
    showInSettings: boolean;
  }>;
  enabledProviders: string[];
  localWarnings: string[];
  editingVariable: GeneralSystemSettingsVariable | null;
  editingVariableOriginalKey: string | null;
  integrationCatalog: ControlPlaneCoreIntegration[];
  integrationConnections: Record<string, ControlPlaneCoreIntegrationConnection>;
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
  submitProviderLoginCode: (providerId: string, sessionId: string, code: string) => Promise<ProviderLoginSession>;
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
  setIntegrationSystemEnabled: (integrationId: string, enabled: boolean) => Promise<void>;
  connectIntegration: (integrationId: string) => Promise<void>;
  ensureIntegrationConnectionFresh: (
    integrationId: string,
    options?: { force?: boolean },
  ) => Promise<ControlPlaneCoreIntegrationConnection | null>;
  verifyIntegrationConnection: (integrationId: string) => Promise<void>;
  disconnectIntegrationConnection: (integrationId: string) => Promise<void>;
  isIntegrationActionPending: (integrationId: string, action: IntegrationAction) => boolean;
  integrationActionStatus: (
    integrationId: string,
    action: IntegrationAction,
  ) => "idle" | "pending" | "success" | "error";
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

function integrationActionKey(
  integrationId: string,
  action: IntegrationAction,
) {
  return `integration:${integrationId}:${action}`;
}

function integrationToggleKey(integrationId: string) {
  return `${integrationId}_enabled`;
}

function normalizeCoreConnection(
  integration: ControlPlaneCoreIntegration,
  connection?: Partial<ControlPlaneCoreIntegrationConnection> | Partial<ControlPlaneAgentConnection> | null,
): ControlPlaneCoreIntegrationConnection {
  const metadata =
    connection?.metadata && typeof connection.metadata === "object" ? connection.metadata : {};
  const legacyConnection =
    connection && "connection_status" in connection
      ? (connection as Partial<ControlPlaneCoreIntegrationConnection>)
      : null;
  const status = String(
    connection && "status" in connection && typeof connection.status === "string"
      ? connection.status
      : typeof legacyConnection?.connection_status === "string"
        ? legacyConnection.connection_status
        : integration.connection_status || "not_configured",
  );
  const authModes = Array.isArray(integration.auth_modes) ? integration.auth_modes : [];
  const authMethod = String(
    (connection && "auth_method" in connection ? connection.auth_method : undefined) ||
      (connection && "auth_strategy" in connection ? connection.auth_strategy : undefined) ||
      integration.auth_mode ||
      authModes[0] ||
      "none",
  );

  return {
    connection_key:
      (connection && "connection_key" in connection ? connection.connection_key : undefined) ||
      `core:${integration.id}`,
    kind: "core",
    integration_key: integration.id,
    integration_id: integration.id,
    title: integration.title,
    description: integration.description || "",
    transport: integration.transport,
    auth_modes: authModes,
    auth_mode: authMethod,
    auth_method: authMethod,
    auth_strategy:
      (connection && "auth_strategy" in connection ? connection.auth_strategy : undefined) || authMethod,
    source_origin:
      (connection && "source_origin" in connection ? connection.source_origin : undefined) || "system_default",
    configured: Boolean(
      (connection && "connected" in connection ? connection.connected : undefined) ??
        (connection && "configured" in connection ? connection.configured : undefined) ??
        (status === "configured" || status === "verified"),
    ),
    verified: status === "verified",
    account_label:
      (connection && "account_label" in connection ? connection.account_label : undefined) || "",
    provider_account_id:
      (connection && "provider_account_id" in connection ? connection.provider_account_id : undefined) || null,
    expires_at:
      (connection && "expires_at" in connection ? connection.expires_at : undefined) || null,
    last_verified_at:
      (connection && "last_verified_at" in connection ? connection.last_verified_at : undefined) || "",
    last_error:
      (connection && "last_error" in connection ? connection.last_error : undefined) || "",
    checked_via: typeof metadata.checked_via === "string" ? metadata.checked_via : "",
    auth_expired: typeof metadata.auth_expired === "boolean" ? metadata.auth_expired : false,
    metadata,
    fields:
      Array.isArray(connection && "fields" in connection ? connection.fields : undefined)
        ? ((connection as { fields?: Array<Record<string, unknown>> }).fields ?? [])
        : (integration.connection?.fields ?? []),
    health_probe:
      typeof metadata.health_probe === "string"
        ? metadata.health_probe
        : integration.health_probe,
    supports_persistence:
      typeof metadata.supports_persistence === "boolean"
        ? metadata.supports_persistence
        : integration.supports_persistence,
    connection_status: status,
    status,
    connected:
      (connection && "connected" in connection ? connection.connected : undefined) ??
      (status === "configured" || status === "verified"),
    enabled:
      (connection && "enabled" in connection ? connection.enabled : undefined) ??
      (connection && "connected" in connection ? connection.connected : undefined) ??
      false,
    tool_count:
      (connection && "tool_count" in connection ? connection.tool_count : undefined) ?? 0,
  };
}

function buildIntegrationConnectionMap(
  coreIntegrations?: ControlPlaneCoreIntegrations | null,
) {
  return Object.fromEntries(
    ((coreIntegrations?.items || []) as ControlPlaneCoreIntegration[]).map((integration) => {
      const connection = normalizeCoreConnection(integration, integration.connection ?? null);
      return [integration.id, connection];
    }),
  ) as Record<string, ControlPlaneCoreIntegrationConnection>;
}

export function SystemSettingsProvider({
  settings,
  coreIntegrations,
  children,
}: {
  settings: GeneralSystemSettings;
  coreIntegrations?: ControlPlaneCoreIntegrations;
  children: ReactNode;
}) {
  const { tl } = useAppI18n();
  const { showToast } = useToast();
  const { runAction, isPending, getStatus } = useAsyncAction();
  const [draft, setDraft] = useState(() => cloneGeneralSystemSettings(settings));
  const [baseline, setBaseline] = useState<GeneralSystemSettings>(() =>
    cloneGeneralSystemSettings(settings),
  );
  const [sectionErrors, setSectionErrors] = useState<
    Record<SettingsSectionId, SystemSettingsFieldError[]>
  >(() => ({ ...EMPTY_SECTION_ERRORS }));
  const clearSectionErrors = useCallback((sectionId?: SettingsSectionId) => {
    if (sectionId) {
      setSectionErrors((prev) => ({ ...prev, [sectionId]: [] }));
    } else {
      setSectionErrors({ ...EMPTY_SECTION_ERRORS });
    }
  }, []);

  const sectionDirty = useMemo(() => {
    const result: Record<SettingsSectionId, boolean> = {
      general: false,
      models: false,
      integrations: false,
      intelligence: false,
      scheduler: false,
      variables: false,
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
  const normalizedStoredSection = STEP_TO_SECTION[storedSection] ?? storedSection;
  const activeSection: SettingsSectionId = isSettingsSectionId(normalizedStoredSection)
    ? normalizedStoredSection
    : DEFAULT_SETTINGS_SECTION_ID;
  const [editingVariable, setEditingVariable] = useState<GeneralSystemSettingsVariable | null>(null);
  const [editingVariableOriginalKey, setEditingVariableOriginalKey] = useState<string | null>(null);
  const [providerConnectionDrafts, setProviderConnectionDrafts] = useState<Record<string, ProviderConnectionDraft>>(
    () => buildProviderConnectionDrafts(settings),
  );
  const [integrationConnections, setIntegrationConnections] = useState<
    Record<string, ControlPlaneCoreIntegrationConnection>
  >(() => buildIntegrationConnectionMap(coreIntegrations));
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
  const autoOpenedUrlsRef = useRef<Record<string, boolean>>({});
  const loginPopupWindowsRef = useRef<Record<string, Window | null>>({});
  const loginPollInFlightRef = useRef<Record<string, boolean>>({});
  const integrationVerificationCacheRef = useRef<Record<string, IntegrationVerificationCacheEntry>>({});
  const integrationVerificationInFlightRef = useRef<
    Record<string, { fingerprint: string; promise: Promise<IntegrationVerificationResponse | null> }>
  >({});
  const elevenlabsVoiceCacheRef = useRef<Record<string, VoiceCatalogCacheEntry>>({});
  const kokoroVoiceCacheRef = useRef<Record<string, KokoroVoiceCatalogCacheEntry>>({});
  const ollamaModelCacheRef = useRef<Record<string, OllamaModelCatalogCacheEntry>>({});
  const providerConnectionDraftsRef = useRef(providerConnectionDrafts);
  providerConnectionDraftsRef.current = providerConnectionDrafts;

  const resetElevenLabsVoiceState = useCallback(
    (selectedLanguage = draft.values.models.elevenlabs_default_language) => {
      elevenlabsVoiceCacheRef.current = {};
      setElevenlabsVoiceCatalog({
        ...EMPTY_ELEVENLABS_VOICE_CATALOG,
        selected_language: selectedLanguage,
        provider_connected: false,
      });
    },
    [draft.values.models.elevenlabs_default_language],
  );

  const resetOllamaModelState = useCallback((connection?: GeneralSystemSettingsProviderConnection | null) => {
    ollamaModelCacheRef.current = {};
    setOllamaModelCatalog({
      ...EMPTY_OLLAMA_MODEL_CATALOG,
      base_url: connection?.base_url || "",
      auth_mode: connection?.auth_mode || "local",
      provider_connected: false,
    });
  }, []);

  useEffect(() => {
    const freshClone = cloneGeneralSystemSettings(settings);
    setBaseline(freshClone);
    setDraft(cloneGeneralSystemSettings(settings));
    setProviderConnectionDrafts(buildProviderConnectionDrafts(settings));
    setElevenlabsVoiceCatalog(EMPTY_ELEVENLABS_VOICE_CATALOG);
      setKokoroVoiceCatalog(EMPTY_KOKORO_VOICE_CATALOG);
      setKokoroDownloadJobs({});
      setOllamaModelCatalog(EMPTY_OLLAMA_MODEL_CATALOG);
      setIntegrationConnections(buildIntegrationConnectionMap(coreIntegrations));
      integrationVerificationCacheRef.current = {};
      integrationVerificationInFlightRef.current = {};
      elevenlabsVoiceCacheRef.current = {};
      kokoroVoiceCacheRef.current = {};
      ollamaModelCacheRef.current = {};
  }, [coreIntegrations, settings]);

  const integrationCatalog = useMemo(
    () => coreIntegrations?.items || [],
    [coreIntegrations],
  );

  const normalizeIntegrationConnectionPayload = useCallback(
    (
      integrationId: string,
      connection: Partial<ControlPlaneAgentConnection> | Partial<ControlPlaneCoreIntegrationConnection> | null | undefined,
    ) => {
      const integration =
        ((integrationCatalog as ControlPlaneCoreIntegration[]).find((item) => item.id === integrationId) || {
          id: integrationId,
          title: integrationId,
          description: "",
          auth_modes: [],
        }) as ControlPlaneCoreIntegration;
      return normalizeCoreConnection(integration, connection);
    },
    [integrationCatalog],
  );

  const providerOptions = useMemo(
    () =>
      draft.catalogs.providers
        .filter((provider) => provider.show_in_settings !== false)
        .map((provider: GeneralSystemSettingsCatalogProvider) => ({
          id: String(provider.id),
          title: String(provider.title || provider.id),
          vendor: String(provider.vendor || ""),
          category: String(provider.category || "general"),
          commandPresent: Boolean(provider.command_present),
          supportsApiKey: Boolean(provider.supports_api_key),
          supportsSubscriptionLogin: Boolean(provider.supports_subscription_login),
          supportsLocalConnection: Boolean(provider.supports_local_connection),
          supportedAuthModes: Array.isArray(provider.supported_auth_modes) ? provider.supported_auth_modes : [],
          loginFlowKind: String(provider.login_flow_kind || ""),
          requiresProjectId: Boolean(provider.requires_project_id),
          connectionManaged: Boolean(provider.connection_managed),
          showInSettings: provider.show_in_settings !== false,
        })),
    [draft.catalogs.providers],
  );
  const providerOptionMap = useMemo(
    () => Object.fromEntries(providerOptions.map((provider) => [provider.id, provider])),
    [providerOptions],
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
          if (!provider.connectionManaged) {
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

  const replaceIntegrationConnection = useCallback((connection: ControlPlaneCoreIntegrationConnection) => {
    setIntegrationConnections((current) => ({
      ...current,
      [connection.integration_id]: connection,
    }));
  }, []);

  const getIntegrationVerificationFingerprint = useCallback(
    (integrationId: string, connection?: ControlPlaneCoreIntegrationConnection | null) => {
      const toggleKey = integrationToggleKey(integrationId);
      const enabled = Boolean(draft.values.resources.integrations[toggleKey]);
      return JSON.stringify({
        enabled,
        configured: Boolean(connection?.configured),
        verified: Boolean(connection?.verified),
        status: connection?.connection_status || "",
        last_verified_at: connection?.last_verified_at || "",
        last_error: connection?.last_error || "",
        checked_via: connection?.checked_via || "",
        auth_expired: Boolean(connection?.auth_expired),
        account_label: connection?.account_label || "",
        metadata: connection?.metadata || {},
      });
    },
    [draft.values.resources.integrations],
  );

  const rememberIntegrationVerification = useCallback(
    (
      integrationId: string,
      connection: ControlPlaneCoreIntegrationConnection,
      fingerprint: string,
      verified: boolean,
    ) => {
      integrationVerificationCacheRef.current[integrationId] = {
        fingerprint,
        expiresAt: Date.now() + (verified ? 5 * 60 * 1000 : 45 * 1000),
        connection,
      };
    },
    [],
  );

  const commitIntegrationEnabled = useCallback(
    (integrationId: string, enabled: boolean) => {
      const syncEnabled = (current: GeneralSystemSettings) => {
        const toggleKey = integrationToggleKey(integrationId);
        return {
          ...current,
          values: {
            ...current.values,
            resources: {
              ...current.values.resources,
              integrations: {
                ...current.values.resources.integrations,
                [toggleKey]: enabled,
              },
            },
          },
        };
      };

      setDraft(syncEnabled);
      setBaseline(syncEnabled);
    },
    [],
  );

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

  const openPendingLoginPopup = useCallback(
    (providerId: string) => {
      if (typeof window === "undefined") {
        return null;
      }
      const existingWindow = loginPopupWindowsRef.current[providerId];
      if (existingWindow && !existingWindow.closed) {
        return existingWindow;
      }
      const popupWindow = window.open("", "_blank", "popup=yes,width=960,height=800");
      if (!popupWindow) {
        return null;
      }
      try {
        popupWindow.document.title = "Abrindo autenticacao";
        popupWindow.document.body.innerHTML = `
          <style>
            html, body {
              height: 100%;
              margin: 0;
              background: #111111;
              color: #f5f5f5;
              font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            body {
              display: grid;
              place-items: center;
              padding: 32px;
            }
            .auth-waiting {
              max-width: 440px;
              text-align: center;
              line-height: 1.6;
              color: rgba(255, 255, 255, 0.84);
            }
          </style>
          <div class="auth-waiting">
            Aguardando a pagina oficial de autenticacao...
          </div>
        `;
        popupWindow.opener = null;
      } catch {
        // Ignore popup rendering issues and fall back to the manual link.
      }
      loginPopupWindowsRef.current[providerId] = popupWindow;
      return popupWindow;
    },
    [],
  );

  const openProviderAuthUrl = useCallback(
    (providerId: string, sessionId: string, authUrl: string) => {
      if (!authUrl || autoOpenedUrlsRef.current[sessionId]) {
        return;
      }

      autoOpenedUrlsRef.current[sessionId] = true;
      const popupWindow = loginPopupWindowsRef.current[providerId];
      if (popupWindow && !popupWindow.closed) {
        try {
          popupWindow.opener = null;
          popupWindow.location.replace(authUrl);
          return;
        } catch {
          // Fall through to a direct open attempt if the held popup can no longer be navigated.
        }
      }
      window.open(authUrl, "_blank", "noopener,noreferrer");
    },
    [],
  );

  const clearProviderLoginWindow = useCallback((providerId: string) => {
    const popupWindow = loginPopupWindowsRef.current[providerId];
    if (!popupWindow || popupWindow.closed) {
      delete loginPopupWindowsRef.current[providerId];
      return;
    }
    try {
      popupWindow.close();
    } catch {
      // Ignore popup closing failures.
    }
    delete loginPopupWindowsRef.current[providerId];
  }, []);

  const verifyProviderConnectionSilently = useCallback(
    async (providerId: string) => {
      const payload = await requestJson<{
        connection: GeneralSystemSettingsProviderConnection;
        verification: Record<string, unknown>;
      }>(`/api/control-plane/providers/${providerId}/connection/verify`, {
        method: "POST",
      });
      const verified = Boolean(payload.verification?.verified);
      const currentLoginSession = providerConnectionDraftsRef.current[providerId]?.login_session || null;
      replaceProviderConnection(payload.connection);
      setProviderConnectionDraft(providerId, {
        project_id: payload.connection.project_id || "",
        base_url: payload.connection.base_url || "",
        login_session: verified ? null : currentLoginSession,
      });
      if (verified) {
        clearProviderLoginWindow(providerId);
      }
      return payload;
    },
    [clearProviderLoginWindow, replaceProviderConnection, setProviderConnectionDraft],
  );

  // Derive a stable key from active login sessions so the polling effect only
  // re-mounts when sessions are added or removed — NOT on every draft update.
  const activeLoginSessionKey = useMemo(() => {
    const keys: string[] = [];
    for (const [providerId, draft] of Object.entries(providerConnectionDrafts)) {
      const s = draft.login_session;
      if (s && s.status !== "completed" && s.status !== "error" && s.status !== "cancelled") {
        keys.push(`${providerId}:${s.session_id}`);
      }
    }
    return keys.sort().join(",");
  }, [providerConnectionDrafts]);

  useEffect(() => {
    if (!activeLoginSessionKey) return;

    let cancelled = false;
    const poll = async () => {
      const currentDrafts = providerConnectionDraftsRef.current;
      const activeSessions = Object.entries(currentDrafts)
        .map(([providerId, d]) => ({ providerId, session: d.login_session }))
        .filter(
          (entry): entry is { providerId: string; session: ProviderLoginSession } =>
            !!entry.session &&
            entry.session.status !== "completed" &&
            entry.session.status !== "error" &&
            entry.session.status !== "cancelled",
        );

      for (const { providerId, session } of activeSessions) {
        const pollKey = `${providerId}:${session.session_id}`;
        if (loginPollInFlightRef.current[pollKey]) {
          continue;
        }
        loginPollInFlightRef.current[pollKey] = true;
        try {
          const refreshed = await requestJson<ProviderLoginSession>(
            `/api/control-plane/providers/${providerId}/connection/login/${session.session_id}`,
          );
          if (cancelled) return;
          const currentSession = providerConnectionDraftsRef.current[providerId]?.login_session || null;
          if (!isEqual(currentSession, refreshed)) {
            setProviderConnectionDraft(providerId, { login_session: refreshed });
          }
          if (refreshed.auth_url && refreshed.status === "awaiting_browser") {
            openProviderAuthUrl(providerId, refreshed.session_id, refreshed.auth_url);
          }
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
          if (["completed", "error", "cancelled"].includes(refreshed.status)) {
            delete loginPollInFlightRef.current[pollKey];
            if (refreshed.status !== "awaiting_browser") {
              clearProviderLoginWindow(providerId);
            }
          }
        } catch {
          // Keep the last visible state until the user retries or verifies manually.
        } finally {
          delete loginPollInFlightRef.current[pollKey];
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
  }, [
    activeLoginSessionKey,
    clearProviderLoginWindow,
    openProviderAuthUrl,
    setProviderConnectionDraft,
    verifyProviderConnectionSilently,
  ]);

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
      const connection = integrationConnections[integrationName];
      if (!connection) continue;
      const missingFields = (connection.fields || [])
        .filter((field) => field.required && !(field.value || field.value_present))
        .map((field) => String(field.label || field.key || integrationName));
      if (missingFields.length > 0) {
        warnings.push(
          tl("{{title}} está habilitado, mas faltam credenciais obrigatórias: {{fields}}.", {
            title: connection.title || integrationName,
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
      const managedProvider = providerOptionMap[selection.provider_id]?.connectionManaged;
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
  }, [draft, enabledProviders, integrationConnections, providerConnections, providerOptionMap, tl]);

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
      setSectionErrors((prev) => ({ ...prev, [sectionId]: [] }));
    },
    [baseline],
  );

  const setField = useCallback(
    <T extends keyof GeneralSystemSettings["values"]>(
      group: T,
      nextGroup: GeneralSystemSettings["values"][T],
    ) => {
      setDraft((prev) => ({
        ...prev,
        values: { ...prev.values, [group]: nextGroup },
      }));
    },
    [],
  );

  const moveFallback = useCallback(
    (providerId: string, direction: "up" | "down") => {
      setDraft((prev) => {
        const list = [...prev.values.models.fallback_order];
        const index = list.indexOf(providerId);
        if (index === -1) return prev;
        const swapWith = direction === "up" ? index - 1 : index + 1;
        if (swapWith < 0 || swapWith >= list.length) return prev;
        [list[index], list[swapWith]] = [list[swapWith], list[index]];
        return {
          ...prev,
          values: {
            ...prev.values,
            models: {
              ...prev.values.models,
              fallback_order: normalizeFallbackOrder(
                enabledProviders,
                list,
                prev.values.models.default_provider,
              ),
            },
          },
        };
      });
    },
    [enabledProviders],
  );

  const toggleGlobalTool = useCallback(
    (toolId: string) => {
      setDraft((prev) => {
        const currentTools = prev.values.resources.global_tools;
        const nextTools = currentTools.includes(toolId)
          ? currentTools.filter((item) => item !== toolId)
          : [...currentTools, toolId];
        return {
          ...prev,
          values: {
            ...prev.values,
            resources: { ...prev.values.resources, global_tools: nextTools },
          },
        };
      });
    },
    [],
  );

  const toggleIntegration = useCallback(
    (integrationKey: string) => {
      setDraft((prev) => ({
        ...prev,
        values: {
          ...prev.values,
          resources: {
            ...prev.values.resources,
            integrations: {
              ...prev.values.resources.integrations,
              [integrationKey]: !prev.values.resources.integrations[integrationKey],
            },
          },
        },
      }));
    },
    [],
  );

  const setIntegrationSystemEnabled = useCallback(
    async (integrationId: string, enabled: boolean) => {
      await runAction(
        integrationActionKey(integrationId, enabled ? "enable" : "disable"),
        async () =>
          requestJson<{
            integration_id: string;
            enabled: boolean;
            connection: ControlPlaneAgentConnection;
          }>(`/api/control-plane/integrations/${integrationId}/system`, {
            method: "POST",
            body: JSON.stringify({ enabled }),
          }),
        {
          successMessage: enabled
            ? tl("Integração ativada no sistema.")
            : tl("Integração desativada no sistema."),
          errorMessage: enabled
            ? tl("Nao foi possivel ativar a integração no sistema.")
            : tl("Nao foi possivel desativar a integração no sistema."),
          onSuccess: ({ enabled: nextEnabled, connection }) => {
            replaceIntegrationConnection(normalizeIntegrationConnectionPayload(integrationId, connection));
            commitIntegrationEnabled(integrationId, Boolean(nextEnabled));
          },
        },
      );
    },
    [commitIntegrationEnabled, normalizeIntegrationConnectionPayload, replaceIntegrationConnection, runAction, tl],
  );

  const connectIntegration = useCallback(
    async (integrationId: string) => {
      const connection = integrationConnections[integrationId];
      await runAction(
        integrationActionKey(integrationId, "connect"),
        async () =>
          requestJson<ControlPlaneAgentConnection>(
            `/api/control-plane/connections/defaults/${encodeURIComponent(`core:${integrationId}`)}`,
            {
              method: "PUT",
              body: JSON.stringify({
                auth_method: connection?.auth_method || connection?.auth_mode || "none",
                fields: (connection?.fields || []).map((field) => ({
                  key: field.key,
                  value: field.value || "",
                  clear: Boolean(field.clear),
                })),
              }),
            },
          ),
        {
          successMessage: tl("Conexão salva. Agora rode a verificação."),
          errorMessage: tl("Nao foi possivel salvar a configuracao da integração."),
          onSuccess: (connection) => {
            replaceIntegrationConnection(normalizeIntegrationConnectionPayload(integrationId, connection));
          },
        },
      );
    },
    [integrationConnections, normalizeIntegrationConnectionPayload, replaceIntegrationConnection, runAction, tl],
  );

  const refreshIntegrationConnectionSilently = useCallback(
    async (integrationId: string) => {
      const payload = await requestJson<IntegrationVerificationResponse>(
        `/api/control-plane/connections/defaults/${encodeURIComponent(`core:${integrationId}`)}/verify`,
        {
          method: "POST",
        },
      );
      const verified = Boolean(payload.verification?.verified);
      const normalizedConnection = normalizeIntegrationConnectionPayload(integrationId, payload.connection as Partial<ControlPlaneAgentConnection>);
      replaceIntegrationConnection(normalizedConnection);
      const fingerprint = getIntegrationVerificationFingerprint(integrationId, normalizedConnection);
      rememberIntegrationVerification(integrationId, normalizedConnection, fingerprint, verified);
      return {
        ...payload,
        connection: normalizedConnection,
      };
    },
    [
      getIntegrationVerificationFingerprint,
      normalizeIntegrationConnectionPayload,
      rememberIntegrationVerification,
      replaceIntegrationConnection,
    ],
  );

  const ensureIntegrationConnectionFresh = useCallback(
    async (
      integrationId: string,
      options?: { force?: boolean },
    ): Promise<ControlPlaneCoreIntegrationConnection | null> => {
      const connection = integrationConnections[integrationId];
      if (!connection || !connection.configured) {
        return null;
      }

      const fingerprint = getIntegrationVerificationFingerprint(integrationId, connection);
      const now = Date.now();
      const cached = integrationVerificationCacheRef.current[integrationId];
      if (!options?.force && cached && cached.fingerprint === fingerprint && cached.expiresAt > now) {
        return cached.connection;
      }

      const verifiedAt = Date.parse(connection.last_verified_at || "");
      const successFresh =
        Boolean(connection.verified) &&
        Boolean(draft.values.resources.integrations[integrationToggleKey(integrationId)]) &&
        Number.isFinite(verifiedAt) &&
        now - verifiedAt < 5 * 60 * 1000;
      if (!options?.force && successFresh) {
        rememberIntegrationVerification(integrationId, connection, fingerprint, true);
        return connection;
      }

      const inFlight = integrationVerificationInFlightRef.current[integrationId];
      if (!options?.force && inFlight && inFlight.fingerprint === fingerprint) {
        const result = await inFlight.promise;
        return result?.connection || null;
      }

      const promise = refreshIntegrationConnectionSilently(integrationId).catch((error) => {
        rememberIntegrationVerification(integrationId, connection, fingerprint, false);
        throw error;
      });
      integrationVerificationInFlightRef.current[integrationId] = { fingerprint, promise };

      try {
        const result = await promise;
        return result.connection;
      } catch {
        return null;
      } finally {
        const current = integrationVerificationInFlightRef.current[integrationId];
        if (current && current.fingerprint === fingerprint) {
          delete integrationVerificationInFlightRef.current[integrationId];
        }
      }
    },
    [
      draft.values.resources.integrations,
      getIntegrationVerificationFingerprint,
      integrationConnections,
      rememberIntegrationVerification,
      refreshIntegrationConnectionSilently,
    ],
  );

  const verifyIntegrationConnection = useCallback(
    async (integrationId: string) => {
      await runAction(
        integrationActionKey(integrationId, "verify"),
        async () => refreshIntegrationConnectionSilently(integrationId),
        {
          successMessage: tl("Integração verificada com sucesso."),
          errorMessage: tl("Nao foi possivel verificar a integração."),
        },
      );
    },
    [refreshIntegrationConnectionSilently, runAction, tl],
  );

  const disconnectIntegrationConnection = useCallback(
    async (integrationId: string) => {
      await runAction(
        integrationActionKey(integrationId, "disconnect"),
        async () =>
          requestJson<{
            connection: ControlPlaneAgentConnection;
          }>(`/api/control-plane/connections/defaults/${encodeURIComponent(`core:${integrationId}`)}`, {
            method: "DELETE",
          }),
        {
          successMessage: tl("Integração desconectada."),
          errorMessage: tl("Nao foi possivel desconectar a integração."),
          onSuccess: ({ connection }) => {
            replaceIntegrationConnection(normalizeIntegrationConnectionPayload(integrationId, connection));
          },
        },
      );
    },
    [normalizeIntegrationConnectionPayload, replaceIntegrationConnection, runAction, tl],
  );

  const setCredentialField = useCallback(
    (
      integrationKey: string,
      fieldKey: string,
      updater: (field: GeneralSystemSettingsCredentialField) => GeneralSystemSettingsCredentialField,
    ) => {
      setIntegrationConnections((prev) => {
        const integration = prev[integrationKey];
        if (!integration) return prev;
        const nextFields = (integration.fields || []).map((field) =>
          field.key === fieldKey ? updater(field as GeneralSystemSettingsCredentialField) : field,
        );
        return {
          ...prev,
          [integrationKey]: {
            ...integration,
            fields: nextFields,
          },
        };
      });
    },
    [],
  );

  const openNewVariable = useCallback(() => {
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
  }, []);

  const openEditVariable = useCallback((variable: GeneralSystemSettingsVariable) => {
    setEditingVariableOriginalKey(variable.key);
    setEditingVariable(sanitizeVariableDraft(variable));
  }, []);

  const confirmVariable = useCallback(() => {
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
    setDraft((prev) => {
      const baseVariables =
        editingVariableOriginalKey && editingVariableOriginalKey !== sanitized.key
          ? removeVariable(prev.values.variables, editingVariableOriginalKey)
          : prev.values.variables;
      return {
        ...prev,
        values: { ...prev.values, variables: upsertVariable(baseVariables, sanitized) },
      };
    });
    setEditingVariableOriginalKey(null);
    setEditingVariable(null);
  }, [editingVariable, editingVariableOriginalKey, showToast, tl]);

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
                // Ask the backend to verify + flip the enabled flag in a
                // single round-trip. Falls back to the explicit verify call
                // below when the backend can't self-verify (legacy or
                // providers that only support subscription login).
                verify_after_save: true,
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
              auth_mode: connection.auth_mode,
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
          onError: async () => {
            if (providerId === "elevenlabs") {
              resetElevenLabsVoiceState();
            } else if (providerId === "ollama") {
              resetOllamaModelState(providerConnections.ollama);
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
      resetElevenLabsVoiceState,
      resetOllamaModelState,
      runAction,
      setProviderConnectionDraft,
      verifyProviderConnectionSilently,
      providerConnections.ollama,
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
              auth_mode: connection.auth_mode,
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
          onError: async () => {
            if (providerId === "ollama") {
              resetOllamaModelState(providerConnections.ollama);
            }
          },
        },
      );
    },
    [
      loadOllamaModels,
      providerConnectionDrafts,
      providerConnections.ollama,
      replaceProviderConnection,
      resetOllamaModelState,
      runAction,
      setProviderConnectionDraft,
      verifyProviderConnectionSilently,
      tl,
    ],
  );

  const startProviderLogin = useCallback(
    async (providerId: string) => {
      const connectionDraft = providerConnectionDrafts[providerId];
      const providerOption = providerOptionMap[providerId];
      if (providerOption?.loginFlowKind === "browser") {
        openPendingLoginPopup(providerId);
      }
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
              auth_mode: connection.auth_mode,
              api_key: "",
              project_id: connection.project_id || connectionDraft?.project_id || "",
              login_session,
            });
            if (login_session.auth_url) {
              openProviderAuthUrl(providerId, login_session.session_id, login_session.auth_url);
            } else if (
              login_session.status === "completed" &&
              !login_session.user_code &&
              !login_session.auth_url
            ) {
              clearProviderLoginWindow(providerId);
            }
          },
          onError: async () => {
            clearProviderLoginWindow(providerId);
          },
        },
      );
    },
    [
      clearProviderLoginWindow,
      openPendingLoginPopup,
      openProviderAuthUrl,
      providerConnectionDrafts,
      providerOptionMap,
      replaceProviderConnection,
      runAction,
      setProviderConnectionDraft,
      tl,
    ],
  );

  const submitProviderLoginCode = useCallback(
    async (providerId: string, sessionId: string, code: string) => {
      const result = await requestJson<ProviderLoginSession>(
        `/api/control-plane/providers/${providerId}/connection/login/${sessionId}/code`,
        { method: "POST", body: JSON.stringify({ code }) },
      );
      setProviderConnectionDraft(providerId, { login_session: result });
      if (result.status === "completed") {
        try {
          await verifyProviderConnectionSilently(providerId);
        } catch {
          // Keep the completed login session visible so the user can retry or inspect context.
        }
      }
      return result;
    },
    [setProviderConnectionDraft, verifyProviderConnectionSilently],
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
            const verified = Boolean(payload.verification?.verified);
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: connection.auth_mode,
              project_id: connection.project_id || "",
              base_url: connection.base_url || "",
              login_session: verified
                ? null
                : providerConnectionDrafts[providerId]?.login_session || null,
            });
            if (providerId === "elevenlabs") {
              elevenlabsVoiceCacheRef.current = {};
              void loadElevenLabsVoices(draft.values.models.elevenlabs_default_language, { force: true });
            } else if (providerId === "ollama") {
              ollamaModelCacheRef.current = {};
              void loadOllamaModels({ force: true });
            }
          },
          onError: async () => {
            if (providerId === "elevenlabs") {
              resetElevenLabsVoiceState();
            } else if (providerId === "ollama") {
              resetOllamaModelState(providerConnections.ollama);
            }
          },
        },
      );
    },
    [
      draft.values.models.elevenlabs_default_language,
      loadElevenLabsVoices,
      loadOllamaModels,
      providerConnections.ollama,
      providerConnectionDrafts,
      replaceProviderConnection,
      resetElevenLabsVoiceState,
      resetOllamaModelState,
      runAction,
      setProviderConnectionDraft,
      tl,
      verifyProviderConnectionSilently,
    ],
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
            clearProviderLoginWindow(providerId);
            replaceProviderConnection(connection);
            setProviderConnectionDraft(providerId, {
              auth_mode: connection.auth_mode,
              api_key: "",
              project_id: connection.project_id || "",
              base_url: connection.base_url || "",
              login_session: null,
            });
            if (providerId === "elevenlabs") {
              resetElevenLabsVoiceState();
            } else if (providerId === "ollama") {
              resetOllamaModelState(connection);
            }
          },
        },
      );
    },
    [
      clearProviderLoginWindow,
      replaceProviderConnection,
      resetElevenLabsVoiceState,
      resetOllamaModelState,
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

  const handleSave = useCallback(async () => {
    const generalDefault = draft.values.models.functional_defaults?.general;
    const candidateProvider = generalDefault?.provider_id || draft.values.models.default_provider;
    const defaultProvider =
      candidateProvider && enabledProviders.includes(candidateProvider)
        ? candidateProvider
        : enabledProviders[0] || "";
    // Drop stale functional_defaults that reference providers no longer enabled.
    // This keeps the payload consistent: providers_enabled is the source of
    // truth, and any selection pointing outside it would be rejected by the
    // backend with "must_be_enabled".
    const sanitizedFunctionalDefaults = Object.fromEntries(
      Object.entries(draft.values.models.functional_defaults ?? {}).filter(
        ([, selection]) =>
          typeof selection?.provider_id === "string" &&
          enabledProviders.includes(selection.provider_id.toLowerCase()),
      ),
    ) as typeof draft.values.models.functional_defaults;
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
        functional_defaults: sanitizedFunctionalDefaults,
      },
      resources: draft.values.resources,
      memory_and_knowledge: draft.values.memory_and_knowledge,
      scheduler: draft.values.scheduler,
      variables: draft.values.variables,
    };

    const clientErrors = validatePayloadClientSide(payload);
    if (clientErrors.length > 0) {
      setSectionErrors(groupErrorsBySection(clientErrors));
      const firstBadSection = sectionForField(clientErrors[0].field);
      setStoredSection(firstBadSection);
      showToast(clientErrors[0].message, "error", { title: tl("Corrija os erros antes de salvar.") });
      return;
    }

    clearSectionErrors();

    await runAction(
      "save-general-settings",
      async () => {
        const response = await fetch("/api/control-plane/system-settings/general", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (response.status === 400) {
          const body = (await response.json().catch(() => null)) as
            | { errors?: SystemSettingsFieldError[] }
            | null;
          const serverErrors = Array.isArray(body?.errors) ? body!.errors : [];
          if (serverErrors.length > 0) {
            setSectionErrors(groupErrorsBySection(serverErrors));
            const firstBadSection = sectionForField(serverErrors[0].field);
            setStoredSection(firstBadSection);
            throw new Error(serverErrors[0].message);
          }
          throw new Error(tl("Nao foi possivel salvar as configuracoes gerais."));
        }
        if (!response.ok) {
          throw new Error(tl("Nao foi possivel salvar as configuracoes gerais."));
        }
        const refreshed = (await response.json()) as GeneralSystemSettings;
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
        clearSectionErrors();
        return refreshed;
      },
      {
        successMessage: tl("Configuracoes gerais salvas com sucesso."),
        errorMessage: tl("Nao foi possivel salvar as configuracoes gerais."),
      },
    );
  }, [draft, enabledProviders, runAction, tl, clearSectionErrors, setStoredSection, showToast]);

  const handleDiscard = useCallback(() => {
    setDraft(cloneGeneralSystemSettings(baseline));
    setProviderConnectionDrafts(buildProviderConnectionDrafts(baseline));
    setElevenlabsVoiceCatalog(EMPTY_ELEVENLABS_VOICE_CATALOG);
    setKokoroVoiceCatalog(EMPTY_KOKORO_VOICE_CATALOG);
    setKokoroDownloadJobs({});
    setOllamaModelCatalog(EMPTY_OLLAMA_MODEL_CATALOG);
    elevenlabsVoiceCacheRef.current = {};
    kokoroVoiceCacheRef.current = {};
    ollamaModelCacheRef.current = {};
  }, [baseline]);

  const kokoroDownloadJobForVoice = useCallback(
    (voiceId: string) => kokoroDownloadJobs[String(voiceId).trim().toLowerCase()] || null,
    [kokoroDownloadJobs],
  );

  const isProviderActionPending = useCallback(
    (providerId: string, action: "connect" | "verify" | "disconnect") =>
      isPending(providerActionKey(providerId, action)),
    [isPending],
  );

  const providerActionStatus = useCallback(
    (providerId: string, action: "connect" | "verify" | "disconnect") =>
      getStatus(providerActionKey(providerId, action)),
    [getStatus],
  );

  const isIntegrationActionPending = useCallback(
    (integrationId: string, action: IntegrationAction) =>
      isPending(integrationActionKey(integrationId, action)),
    [isPending],
  );

  const integrationActionStatus = useCallback(
    (integrationId: string, action: IntegrationAction) =>
      getStatus(integrationActionKey(integrationId, action)),
    [getStatus],
  );

  const saving = isPending("save-general-settings");
  const saveStatus = getStatus("save-general-settings");

  const value = useMemo<SystemSettingsContextValue>(() => ({
    draft,
    dirty,
    sectionDirty,
    isDirty,
    discardSection,
    sectionErrors,
    clearSectionErrors,
    saving,
    saveStatus,
    activeSection,
    setActiveSection: setStoredSection,
    providerOptions,
    enabledProviders,
    localWarnings,
    editingVariable,
    editingVariableOriginalKey,
    integrationCatalog,
    integrationConnections,
    providerConnections,
    providerConnectionDrafts,
    elevenlabsVoiceCatalog,
    elevenlabsVoicesLoading,
    kokoroVoiceCatalog,
    kokoroVoicesLoading,
    kokoroDownloadJobForVoice,
    ollamaModelCatalog,
    ollamaModelsLoading,
    setField,
    setProviderConnectionDraft,
    connectProviderApiKey,
    connectProviderLocal,
    startProviderLogin,
    submitProviderLoginCode,
    verifyProviderConnection,
    disconnectProviderConnection,
    loadElevenLabsVoices,
    loadKokoroVoices,
    downloadKokoroVoice,
    loadOllamaModels,
    isProviderActionPending,
    providerActionStatus,
    moveFallback,
    toggleGlobalTool,
    toggleIntegration,
    setIntegrationSystemEnabled,
    connectIntegration,
    ensureIntegrationConnectionFresh,
    verifyIntegrationConnection,
    disconnectIntegrationConnection,
    isIntegrationActionPending,
    integrationActionStatus,
    setCredentialField,
    openNewVariable,
    openEditVariable,
    setEditingVariable,
    confirmVariable,
    handleSave,
    handleDiscard,
    showToast,
  }), [
    draft,
    dirty,
    sectionDirty,
    isDirty,
    discardSection,
    sectionErrors,
    clearSectionErrors,
    saving,
    saveStatus,
    activeSection,
    setStoredSection,
    providerOptions,
    enabledProviders,
    localWarnings,
    editingVariable,
    editingVariableOriginalKey,
    integrationCatalog,
    integrationConnections,
    providerConnections,
    providerConnectionDrafts,
    elevenlabsVoiceCatalog,
    elevenlabsVoicesLoading,
    kokoroVoiceCatalog,
    kokoroVoicesLoading,
    kokoroDownloadJobForVoice,
    ollamaModelCatalog,
    ollamaModelsLoading,
    setField,
    setProviderConnectionDraft,
    connectProviderApiKey,
    connectProviderLocal,
    startProviderLogin,
    submitProviderLoginCode,
    verifyProviderConnection,
    disconnectProviderConnection,
    loadElevenLabsVoices,
    loadKokoroVoices,
    downloadKokoroVoice,
    loadOllamaModels,
    isProviderActionPending,
    providerActionStatus,
    moveFallback,
    toggleGlobalTool,
    toggleIntegration,
    setIntegrationSystemEnabled,
    connectIntegration,
    ensureIntegrationConnectionFresh,
    verifyIntegrationConnection,
    disconnectIntegrationConnection,
    isIntegrationActionPending,
    integrationActionStatus,
    setCredentialField,
    openNewVariable,
    openEditVariable,
    setEditingVariable,
    confirmVariable,
    handleSave,
    handleDiscard,
    showToast,
  ]);

  return <SystemSettingsContext.Provider value={value}>{children}</SystemSettingsContext.Provider>;
}

export function useSystemSettings() {
  const ctx = useContext(SystemSettingsContext);
  if (!ctx) throw new Error("useSystemSettings must be used within SystemSettingsProvider");
  return ctx;
}
