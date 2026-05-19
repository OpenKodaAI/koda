import "server-only";

import { ControlPlaneRequestError, getControlPlaneAgents } from "@/lib/control-plane";

function isControlPlaneFetchFailure(error: unknown) {
  return (
    error instanceof ControlPlaneRequestError ||
    (error instanceof Error &&
      (error.name === "ControlPlaneRequestError" ||
        error.message.toLowerCase().includes("fetch failed")))
  );
}

export async function getCachedAgentDisplays() {
  try {
    const agents = await getControlPlaneAgents();
    return agents.map((agent) => ({
      id: agent.id,
      label: String(agent.appearance?.label || agent.display_name || agent.id),
      color: String(agent.appearance?.color || "#A7ADB4"),
      colorRgb: String(agent.appearance?.color_rgb || "167, 173, 180"),
    }));
  } catch (error) {
    if (!isControlPlaneFetchFailure(error)) {
      throw error;
    }

    return [];
  }
}
