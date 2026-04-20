export type ControlPlaneFetchTier = "catalog" | "detail" | "live";

export const CONTROL_PLANE_CACHE_TAGS = {
  catalog: "control-plane:catalog",
  workspaces: "control-plane:workspaces",
  system: "control-plane:system",
  systemGeneral: "control-plane:system-general",
  core: "control-plane:core",
  agentCatalog: "dashboard:agent-catalog",
  agent: (agentId: string) => `control-plane:agent:${agentId.toUpperCase()}`,
} as const;

const CONTROL_PLANE_REVALIDATE_SECONDS = {
  catalog: 15,
  detail: 5,
} as const;

type ControlPlaneFetchConfig = {
  cache?: RequestCache;
  next?: {
    revalidate: number;
    tags: string[];
  };
};

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

export function getControlPlaneFetchConfig(
  tier: ControlPlaneFetchTier,
  tags: string[] = [],
): ControlPlaneFetchConfig {
  if (tier === "live") {
    return { cache: "no-store" };
  }

  return {
    cache: "force-cache",
    next: {
      revalidate:
        tier === "catalog"
          ? CONTROL_PLANE_REVALIDATE_SECONDS.catalog
          : CONTROL_PLANE_REVALIDATE_SECONDS.detail,
      tags: unique(tags),
    },
  };
}

export function getControlPlaneMutationInvalidation(pathSegments: string[]) {
  const tags = new Set<string>();
  const paths = new Set<string>(["/control-plane"]);

  const [root, maybeBotId, ...rest] = pathSegments;
  if (root === "agents") {
    tags.add(CONTROL_PLANE_CACHE_TAGS.catalog);
    tags.add(CONTROL_PLANE_CACHE_TAGS.agentCatalog);

    if (maybeBotId && !["clone"].includes(maybeBotId)) {
      tags.add(CONTROL_PLANE_CACHE_TAGS.agent(maybeBotId));
      paths.add(`/control-plane/agents/${maybeBotId}`);
    }

    if (rest.includes("runtime-access")) {
      // Runtime access is server-only and should never be proxied to the browser.
      return { tags: [], paths: [] };
    }
  }

  if (root === "system-settings") {
    tags.add(CONTROL_PLANE_CACHE_TAGS.system);
    tags.add(CONTROL_PLANE_CACHE_TAGS.systemGeneral);
    paths.add("/control-plane/system");
  }

  if (root === "workspaces") {
    tags.add(CONTROL_PLANE_CACHE_TAGS.catalog);
    tags.add(CONTROL_PLANE_CACHE_TAGS.workspaces);
    paths.add("/control-plane");
  }

  if (root === "global-defaults") {
    tags.add(CONTROL_PLANE_CACHE_TAGS.system);
  }

  if (root === "core") {
    tags.add(CONTROL_PLANE_CACHE_TAGS.core);
  }

  if (root === "providers") {
    tags.add(CONTROL_PLANE_CACHE_TAGS.systemGeneral);
    tags.add(CONTROL_PLANE_CACHE_TAGS.core);
    paths.add("/control-plane/system");
  }

  return {
    tags: Array.from(tags),
    paths: Array.from(paths),
  };
}
