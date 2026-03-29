import "server-only";

import { ControlPlaneRequestError, getControlPlaneBots } from "@/lib/control-plane";

let didWarnBotCatalogUnavailable = false;

function isControlPlaneFetchFailure(error: unknown) {
  return (
    error instanceof ControlPlaneRequestError ||
    (error instanceof Error &&
      (error.name === "ControlPlaneRequestError" ||
        error.message.toLowerCase().includes("fetch failed")))
  );
}

export async function getCachedBotDisplays() {
  try {
    const bots = await getControlPlaneBots();
    return bots.map((bot) => ({
      id: bot.id,
      label: String(bot.appearance?.label || bot.display_name || bot.id),
      color: String(bot.appearance?.color || "#A7ADB4"),
      colorRgb: String(bot.appearance?.color_rgb || "167, 173, 180"),
    }));
  } catch (error) {
    if (!isControlPlaneFetchFailure(error)) {
      throw error;
    }

    if (!didWarnBotCatalogUnavailable) {
      didWarnBotCatalogUnavailable = true;
      console.warn("bot_catalog_cache_unavailable", {
        message: error instanceof Error ? error.message : String(error),
      });
    }
    return [];
  }
}
