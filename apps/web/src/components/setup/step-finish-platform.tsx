"use client";

import { useMemo, useState, type FormEvent } from "react";
import { ArrowRight, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";
import type {
  ControlPlaneOnboardingStatus,
  ControlPlaneAuthStatus,
} from "@/lib/control-plane";
import { cn } from "@/lib/utils";

type BootstrapAuthMode = "api_key" | "local";
type Section = "access" | "provider" | "agent";

interface StepFinishPlatformProps {
  initialStatus: ControlPlaneOnboardingStatus | null;
  authStatus: ControlPlaneAuthStatus | null;
  onFinished: () => void;
}

const SUPPORTED_MODES: BootstrapAuthMode[] = ["api_key", "local"];

function providerSupportsBootstrap(
  provider: ControlPlaneOnboardingStatus["providers"][number],
): boolean {
  return provider.supported_auth_modes.some((mode) =>
    SUPPORTED_MODES.includes(mode as BootstrapAuthMode),
  );
}

function suggestedProviderId(status: ControlPlaneOnboardingStatus | null): string {
  if (!status) return "";
  if (status.system.default_provider) return status.system.default_provider;
  const verified = status.providers.find((p) => p.verified);
  if (verified) return verified.provider_id;
  const configured = status.providers.find((p) => p.configured);
  if (configured) return configured.provider_id;
  const bootstrap = status.providers.find(providerSupportsBootstrap);
  return bootstrap?.provider_id ?? status.providers[0]?.provider_id ?? "";
}

function suggestedAuthMode(
  provider: ControlPlaneOnboardingStatus["providers"][number] | undefined,
): BootstrapAuthMode {
  const supported = (provider?.supported_auth_modes ?? []).filter((mode) =>
    SUPPORTED_MODES.includes(mode as BootstrapAuthMode),
  ) as BootstrapAuthMode[];
  if (supported.includes("api_key")) return "api_key";
  if (supported.includes("local")) return "local";
  return "api_key";
}

export function StepFinishPlatform({
  initialStatus,
  authStatus,
  onFinished,
}: StepFinishPlatformProps) {
  const { t } = useAppI18n();
  const [section, setSection] = useState<Section>("access");

  // Access
  const [allowedUserIds, setAllowedUserIds] = useState(
    initialStatus?.system.allowed_user_ids.join(", ") ?? "",
  );

  // Owner meta (reuses authStatus)
  const [ownerName, setOwnerName] = useState(initialStatus?.system.owner_name ?? "");
  const [ownerEmail, setOwnerEmail] = useState(initialStatus?.system.owner_email ?? "");
  const [ownerGithub, setOwnerGithub] = useState(initialStatus?.system.owner_github ?? "");

  // Provider
  const bootstrapProviders = useMemo(
    () => (initialStatus?.providers ?? []).filter(providerSupportsBootstrap),
    [initialStatus],
  );
  const [providerId, setProviderId] = useState(suggestedProviderId(initialStatus));
  const selectedProvider = bootstrapProviders.find((p) => p.provider_id === providerId);
  const [authMode, setAuthMode] = useState<BootstrapAuthMode>(
    suggestedAuthMode(selectedProvider),
  );
  const [apiKey, setApiKey] = useState("");
  const [projectId, setProjectId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  // Agent
  const [createAgentNow, setCreateAgentNow] = useState(false);
  const [agentId, setAgentId] = useState("AGENT_A");
  const defaultAgentName = initialStatus?.system.owner_name
    ? `${initialStatus.system.owner_name}'s Agent`
    : "Koda Agent";
  const [agentDisplayName, setAgentDisplayName] = useState(defaultAgentName);
  const [agentTelegramToken, setAgentTelegramToken] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const storageReady = Boolean(
    initialStatus?.storage.database.ready && initialStatus?.storage.object_storage.ready,
  );
  const providerRequiresApiKey =
    authMode === "api_key" &&
    !selectedProvider?.configured &&
    !selectedProvider?.verified &&
    !apiKey.trim();
  const canSubmit =
    Boolean(authStatus?.authenticated) &&
    storageReady &&
    Boolean(providerId.trim()) &&
    Boolean(allowedUserIds.trim()) &&
    !providerRequiresApiKey;

  const sectionItems = [
    { id: "access", label: t("setup.finishPlatform.sections.access") },
    { id: "provider", label: t("setup.finishPlatform.sections.provider") },
    { id: "agent", label: t("setup.finishPlatform.sections.agent") },
  ];

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!canSubmit) {
      setError(t("setup.errors.bootstrapIncomplete"));
      return;
    }
    setBusy(true);
    try {
      await requestJson<{ ok: boolean; status: ControlPlaneOnboardingStatus }>(
        "/api/control-plane/onboarding/bootstrap",
        {
          method: "POST",
          body: JSON.stringify({
            account: {
              owner_name: ownerName.trim(),
              owner_email: ownerEmail.trim(),
              owner_github: ownerGithub.trim(),
            },
            access: { allowed_user_ids: allowedUserIds },
            provider: {
              provider_id: providerId,
              auth_mode: authMode,
              api_key: apiKey.trim(),
              project_id: projectId.trim(),
              base_url: baseUrl.trim(),
            },
            agent: createAgentNow
              ? {
                  agent_id: agentId.trim(),
                  display_name: agentDisplayName.trim(),
                  telegram_token: agentTelegramToken.trim(),
                }
              : {},
          }),
        },
      );
      onFinished();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : t("setup.errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full flex-col gap-6" noValidate>
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
          <Rocket className="icon-sm" />
        </span>
        <h1 className="m-0 text-[var(--font-size-display-sm)] font-medium leading-[1.15] tracking-[var(--tracking-display)] text-[var(--text-primary)]">
          {t("setup.finishPlatform.title")}
        </h1>
        <p className="m-0 max-w-[360px] text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {t("setup.finishPlatform.subtitle")}
        </p>
      </div>

      <SoftTabs
        items={sectionItems}
        value={section}
        onChange={(id) => setSection(id as Section)}
        ariaLabel={t("setup.finishPlatform.title")}
        className="self-center"
      />

      <div className="flex flex-col gap-3">
        {section === "access" ? (
          <>
            <Field label={t("setup.finishPlatform.fields.allowedUserIds")}>
              <Input
                sizeVariant="md"
                value={allowedUserIds}
                onChange={(event) => setAllowedUserIds(event.target.value)}
                placeholder="123456789, 987654321"
                disabled={busy}
              />
              <Hint>{t("setup.finishPlatform.hints.allowedUserIds")}</Hint>
            </Field>
            <Field label={t("setup.finishPlatform.fields.ownerName")}>
              <Input
                sizeVariant="md"
                value={ownerName}
                onChange={(event) => setOwnerName(event.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label={t("setup.finishPlatform.fields.ownerEmail")}>
              <Input
                sizeVariant="md"
                type="email"
                value={ownerEmail}
                onChange={(event) => setOwnerEmail(event.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label={t("setup.finishPlatform.fields.ownerGithub")} optional>
              <Input
                sizeVariant="md"
                value={ownerGithub}
                onChange={(event) => setOwnerGithub(event.target.value)}
                disabled={busy}
              />
            </Field>
          </>
        ) : null}

        {section === "provider" ? (
          <>
            {bootstrapProviders.length > 0 ? (
              <Field label={t("setup.finishPlatform.fields.provider")}>
                <div className="grid gap-1.5">
                  {bootstrapProviders.map((provider) => (
                    <label
                      key={provider.provider_id}
                      className={cn(
                        "flex cursor-pointer items-center gap-3 rounded-[var(--radius-panel-sm)] border px-3 py-2.5 transition-[border-color,background-color]",
                        providerId === provider.provider_id
                          ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                          : "border-[var(--border-subtle)] bg-[var(--panel-soft)] hover:border-[var(--border-strong)]",
                      )}
                    >
                      <input
                        type="radio"
                        name="provider"
                        value={provider.provider_id}
                        checked={providerId === provider.provider_id}
                        onChange={() => {
                          setProviderId(provider.provider_id);
                          setAuthMode(suggestedAuthMode(provider));
                        }}
                        className="accent-[var(--accent)]"
                      />
                      <div className="flex flex-1 flex-col">
                        <span className="text-[0.8125rem] font-medium text-[var(--text-primary)]">
                          {provider.title || provider.provider_id}
                        </span>
                        {provider.verified ? (
                          <span className="text-[0.6875rem] text-[var(--tone-success-dot)]">
                            {t("setup.finishPlatform.providerVerified")}
                          </span>
                        ) : provider.configured ? (
                          <span className="text-[0.6875rem] text-[var(--text-quaternary)]">
                            {t("setup.finishPlatform.providerConfigured")}
                          </span>
                        ) : null}
                      </div>
                    </label>
                  ))}
                </div>
              </Field>
            ) : null}

            <Field label={t("setup.finishPlatform.fields.authMode")}>
              <SoftTabs
                items={[
                  { id: "api_key", label: t("setup.finishPlatform.authModes.api_key") },
                  { id: "local", label: t("setup.finishPlatform.authModes.local") },
                ]}
                value={authMode}
                onChange={(id) => setAuthMode(id as BootstrapAuthMode)}
                ariaLabel={t("setup.finishPlatform.fields.authMode")}
              />
            </Field>

            {authMode === "api_key" ? (
              <>
                <Field label={t("setup.finishPlatform.fields.apiKey")}>
                  <Input
                    sizeVariant="md"
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="sk-…"
                    disabled={busy}
                  />
                  {selectedProvider?.configured ? (
                    <Hint>{t("setup.finishPlatform.hints.apiKeyOptionalWhenConfigured")}</Hint>
                  ) : null}
                </Field>
                <Field label={t("setup.finishPlatform.fields.projectId")} optional>
                  <Input
                    sizeVariant="md"
                    value={projectId}
                    onChange={(event) => setProjectId(event.target.value)}
                    disabled={busy}
                  />
                </Field>
                <Field label={t("setup.finishPlatform.fields.baseUrl")} optional>
                  <Input
                    sizeVariant="md"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://api.anthropic.com"
                    disabled={busy}
                  />
                </Field>
              </>
            ) : null}
          </>
        ) : null}

        {section === "agent" ? (
          <>
            <label className="flex items-center gap-2 text-[0.8125rem] text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={createAgentNow}
                onChange={(event) => setCreateAgentNow(event.target.checked)}
                className="accent-[var(--accent)]"
              />
              {t("setup.finishPlatform.fields.createAgentNow")}
            </label>

            {createAgentNow ? (
              <>
                <Field label={t("setup.finishPlatform.fields.agentId")}>
                  <Input
                    sizeVariant="md"
                    value={agentId}
                    onChange={(event) => setAgentId(event.target.value.toUpperCase())}
                    disabled={busy}
                    className="font-mono"
                  />
                </Field>
                <Field label={t("setup.finishPlatform.fields.agentDisplayName")}>
                  <Input
                    sizeVariant="md"
                    value={agentDisplayName}
                    onChange={(event) => setAgentDisplayName(event.target.value)}
                    disabled={busy}
                  />
                </Field>
                <Field label={t("setup.finishPlatform.fields.agentTelegramToken")} optional>
                  <Input
                    sizeVariant="md"
                    type="password"
                    value={agentTelegramToken}
                    onChange={(event) => setAgentTelegramToken(event.target.value)}
                    disabled={busy}
                  />
                </Field>
              </>
            ) : (
              <Hint>{t("setup.finishPlatform.hints.agentOptional")}</Hint>
            )}
          </>
        ) : null}
      </div>

      {!storageReady ? (
        <InlineAlert tone="warning">
          {t("setup.errors.storageNotReady")}
        </InlineAlert>
      ) : null}

      {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

      <Button
        type="submit"
        variant="accent"
        size="lg"
        disabled={busy || !canSubmit}
        className="w-full"
      >
        {busy ? t("setup.finishPlatform.submitting") : t("setup.finishPlatform.submit")}
        {!busy ? <ArrowRight className="icon-sm ms-1" /> : null}
      </Button>
    </form>
  );
}

function Field({
  label,
  optional,
  children,
}: {
  label: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center justify-between text-[0.75rem] font-medium text-[var(--text-secondary)]">
        {label}
        {optional ? (
          <span className="text-[0.6875rem] text-[var(--text-quaternary)]">optional</span>
        ) : null}
      </span>
      {children}
    </label>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <span className="text-[0.6875rem] text-[var(--text-quaternary)]">{children}</span>;
}
