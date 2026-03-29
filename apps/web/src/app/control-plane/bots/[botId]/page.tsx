import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { BotEditorShell } from "@/components/control-plane/editor/bot-editor-shell";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import {
  ControlPlaneRequestError,
  getControlPlaneBot,
  getControlPlaneCompiledPrompt,
  getControlPlaneCoreCapabilities,
  getControlPlaneCorePolicies,
  getControlPlaneCoreProviders,
  getControlPlaneSystemSettings,
  getControlPlaneCoreTools,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";
import { LOCALE_COOKIE_KEY, translateForLanguage } from "@/lib/i18n";

export default async function ControlPlaneBotPage({
  params,
}: {
  params: Promise<{ botId: string }>;
}) {
  const cookieStore = await cookies();
  const language = cookieStore.get(LOCALE_COOKIE_KEY)?.value;
  const { botId } = await params;
  let payload:
      | {
        bot: Awaited<ReturnType<typeof getControlPlaneBot>>;
        compiledPromptPayload: Awaited<ReturnType<typeof getControlPlaneCompiledPrompt>> | null;
        systemSettings: Awaited<ReturnType<typeof getControlPlaneSystemSettings>>;
        coreTools: Awaited<ReturnType<typeof getControlPlaneCoreTools>>;
        coreProviders: Awaited<ReturnType<typeof getControlPlaneCoreProviders>>;
        corePolicies: Awaited<ReturnType<typeof getControlPlaneCorePolicies>>;
        coreCapabilities: Awaited<ReturnType<typeof getControlPlaneCoreCapabilities>>;
        workspaces: Awaited<ReturnType<typeof getControlPlaneWorkspaces>>;
      }
    | null = null;

  try {
    const [bot, systemSettings, coreTools, coreProviders, corePolicies, coreCapabilities, workspaces] = await Promise.all([
      getControlPlaneBot(botId),
      getControlPlaneSystemSettings(),
      getControlPlaneCoreTools(),
      getControlPlaneCoreProviders(),
      getControlPlaneCorePolicies(),
      getControlPlaneCoreCapabilities(),
      getControlPlaneWorkspaces(),
    ]);
    const compiledPromptPayload = await getControlPlaneCompiledPrompt(botId).catch(() => null);
    payload = { bot, compiledPromptPayload, systemSettings, coreTools, coreProviders, corePolicies, coreCapabilities, workspaces };
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 404) {
      notFound();
    }

    const description =
      error instanceof Error
        ? error.message
        : translateForLanguage(language, "controlPlane.bot.loadDescription", {
            defaultValue: "Could not load the configuration for bot {{botId}}.",
            botId,
          });
    return (
      <ControlPlaneUnavailable
        title={translateForLanguage(language, "controlPlane.bot.loadTitle", {
          defaultValue: "Failed to load {{botId}}",
          botId,
        })}
        description={description}
      />
    );
  }

  if (!payload) {
    return (
      <ControlPlaneUnavailable
        title={translateForLanguage(language, "controlPlane.bot.loadTitle", {
          defaultValue: "Failed to load {{botId}}",
          botId,
        })}
        description={translateForLanguage(language, "controlPlane.bot.loadDescription", {
          defaultValue: "Could not load the configuration for bot {{botId}}.",
          botId,
        })}
      />
    );
  }

  return (
    <BotEditorShell
      bot={payload.bot}
      compiledPromptPayload={payload.compiledPromptPayload}
      core={{
        tools: payload.coreTools,
        providers: payload.coreProviders,
        policies: payload.corePolicies,
        capabilities: payload.coreCapabilities,
      }}
      workspaces={payload.workspaces}
      systemSettings={payload.systemSettings}
    />
  );
}
