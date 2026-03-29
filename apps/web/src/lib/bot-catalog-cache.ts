import "server-only";

import { unstable_cache } from "next/cache";
import { ControlPlaneRequestError, getControlPlaneBots } from "@/lib/control-plane";
import { CONTROL_PLANE_CACHE_TAGS } from "@/lib/control-plane-cache";

let didWarnBotCatalogUnavailable = false;

function isControlPlaneFetchFailure(error: unknown) {
  return (
    error instanceof ControlPlaneRequestError ||
    (error instanceof Error &&
      (error.name === "ControlPlaneRequestError" ||
        error.message.toLowerCase().includes("fetch failed")))
  );
}

const readCachedBotDisplays = unstable_cache(
  async () => {
    const bots = await getControlPlaneBots();
    return bots.map((bot) => ({
      id: bot.id,
      label: String(bot.appearance?.label || bot.display_name || bot.id),
      color: String(bot.appearance?.color || "#A7ADB4"),
      colorRgb: String(bot.appearance?.color_rgb || "167, 173, 180"),
    }));
  },
  ["dashboard-bot-displays"],
  {
    revalidate: 15,
    tags: [CONTROL_PLANE_CACHE_TAGS.botCatalog],
  },
);

export async function getCachedBotDisplays() {
  try {
    return await readCachedBotDisplays();
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
