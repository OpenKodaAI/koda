/**
 * Stub catalog of MCP connectors available to a routine.
 *
 * The real catalog must be sourced from the per-agent integration registry
 * (e.g. GET /api/runtime/agents/{botId}/integrations). For the UI-only phase
 * we expose a static list that mirrors the visible connectors used by the
 * routines feature in the design reference.
 *
 * TODO(api): replace with a hook backed by the runtime endpoint once the
 * contract for per-agent MCP availability is defined.
 */

export interface RoutineConnectorOption {
  id: string;
  label: string;
  category: "design" | "productivity" | "data" | "developer" | "general";
}

const CATALOG: RoutineConnectorOption[] = [
  { id: "excalidraw", label: "Excalidraw", category: "design" },
  { id: "figma", label: "Figma", category: "design" },
  { id: "gmail", label: "Gmail", category: "productivity" },
  { id: "google_calendar", label: "Google Calendar", category: "productivity" },
  { id: "granola", label: "Granola", category: "productivity" },
  { id: "supabase", label: "Supabase", category: "data" },
  { id: "threejs_3d_viewer", label: "Three.js 3D Viewer", category: "developer" },
  { id: "vercel", label: "Vercel", category: "developer" },
];

export function listAvailableConnectors(_agentId: string | null): RoutineConnectorOption[] {
  return CATALOG;
}

export function findConnector(id: string): RoutineConnectorOption | null {
  return CATALOG.find((entry) => entry.id === id) ?? null;
}
