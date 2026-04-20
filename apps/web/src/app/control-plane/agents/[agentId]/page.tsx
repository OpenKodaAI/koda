export const dynamic = "force-dynamic";

import { notFound, redirect } from "next/navigation";
import { AgentEditorShell } from "@/components/control-plane/editor/agent-editor-shell";
import {
  ControlPlaneRequestError,
  getControlPlaneAgent,
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

export default async function ControlPlaneAgentPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId: agentId } = await params;
  let payload: {
    agent: Awaited<ReturnType<typeof getControlPlaneAgent>>;
    compiledPromptPayload: Awaited<ReturnType<typeof getControlPlaneCompiledPrompt>> | null;
    executionPolicyPayload: Awaited<ReturnType<typeof getControlPlaneExecutionPolicy>> | null;
    systemSettings: Awaited<ReturnType<typeof getControlPlaneSystemSettings>>;
    coreTools: Awaited<ReturnType<typeof getControlPlaneCoreTools>>;
    coreProviders: Awaited<ReturnType<typeof getControlPlaneCoreProviders>>;
    corePolicies: Awaited<ReturnType<typeof getControlPlaneCorePolicies>>;
    coreCapabilities: Awaited<ReturnType<typeof getControlPlaneCoreCapabilities>>;
    coreIntegrations: Awaited<ReturnType<typeof getControlPlaneCoreIntegrations>>;
    workspaces: Awaited<ReturnType<typeof getControlPlaneWorkspaces>>;
  };

  try {
    const [
      agent,
      systemSettings,
      coreTools,
      coreProviders,
      corePolicies,
      coreCapabilities,
      coreIntegrations,
      workspaces,
      executionPolicyPayload,
    ] = await Promise.all([
      getControlPlaneAgent(agentId),
      getControlPlaneSystemSettings(),
      getControlPlaneCoreTools(),
      getControlPlaneCoreProviders(),
      getControlPlaneCorePolicies(),
      getControlPlaneCoreCapabilities(),
      getControlPlaneCoreIntegrations(),
      getControlPlaneWorkspaces(),
      getControlPlaneExecutionPolicy(agentId).catch(() => null),
    ]);
    const compiledPromptPayload = await getControlPlaneCompiledPrompt(agentId).catch(() => null);
    payload = {
      agent,
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
    if (error instanceof ControlPlaneRequestError) {
      if (error.status === 404) notFound();
      if (error.status === 401) redirect("/login");
    }
    throw error;
  }

  return (
    <AgentEditorShell
      agent={payload.agent}
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
