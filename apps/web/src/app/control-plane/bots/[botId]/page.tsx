export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import { BotEditorShell } from "@/components/control-plane/editor/bot-editor-shell";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import {
  ControlPlaneRequestError,
  getControlPlaneBot,
  getControlPlaneExecutionPolicy,
  getControlPlaneCompiledPrompt,
  getControlPlaneCoreCapabilities,
  getControlPlaneCoreIntegrations,
  getControlPlaneCorePolicies,
  getControlPlaneCoreProviders,
  getControlPlaneSystemSettings,
  getControlPlaneCoreTools,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";

export default async function ControlPlaneBotPage({
  params,
}: {
  params: Promise<{ botId: string }>;
}) {
  const { botId } = await params;
  let payload:
      | {
        bot: Awaited<ReturnType<typeof getControlPlaneBot>>;
        compiledPromptPayload: Awaited<ReturnType<typeof getControlPlaneCompiledPrompt>> | null;
        executionPolicyPayload: Awaited<ReturnType<typeof getControlPlaneExecutionPolicy>> | null;
        systemSettings: Awaited<ReturnType<typeof getControlPlaneSystemSettings>>;
        coreTools: Awaited<ReturnType<typeof getControlPlaneCoreTools>>;
        coreProviders: Awaited<ReturnType<typeof getControlPlaneCoreProviders>>;
        corePolicies: Awaited<ReturnType<typeof getControlPlaneCorePolicies>>;
        coreCapabilities: Awaited<ReturnType<typeof getControlPlaneCoreCapabilities>>;
        coreIntegrations: Awaited<ReturnType<typeof getControlPlaneCoreIntegrations>>;
        workspaces: Awaited<ReturnType<typeof getControlPlaneWorkspaces>>;
      }
    | null = null;

  try {
    const [
      bot,
      systemSettings,
      coreTools,
      coreProviders,
      corePolicies,
      coreCapabilities,
      coreIntegrations,
      workspaces,
      executionPolicyPayload,
    ] = await Promise.all([
      getControlPlaneBot(botId),
      getControlPlaneSystemSettings(),
      getControlPlaneCoreTools(),
      getControlPlaneCoreProviders(),
      getControlPlaneCorePolicies(),
      getControlPlaneCoreCapabilities(),
      getControlPlaneCoreIntegrations(),
      getControlPlaneWorkspaces(),
      getControlPlaneExecutionPolicy(botId).catch(() => null),
    ]);
    const compiledPromptPayload = await getControlPlaneCompiledPrompt(botId).catch(() => null);
    payload = {
      bot,
      compiledPromptPayload,
      executionPolicyPayload,
      systemSettings,
      coreTools,
      coreProviders,
      corePolicies,
      coreCapabilities,
      coreIntegrations,
      workspaces,
    };
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 404) {
      notFound();
    }

    return <ControlPlaneUnavailable />;
  }

  if (!payload) {
    return <ControlPlaneUnavailable />;
  }

  return (
    <BotEditorShell
      bot={payload.bot}
      compiledPromptPayload={payload.compiledPromptPayload}
      executionPolicyPayload={payload.executionPolicyPayload}
      core={{
        tools: payload.coreTools,
        providers: payload.coreProviders,
        policies: payload.corePolicies,
        capabilities: payload.coreCapabilities,
        integrations: payload.coreIntegrations,
      }}
      workspaces={payload.workspaces}
      systemSettings={payload.systemSettings}
    />
  );
}
