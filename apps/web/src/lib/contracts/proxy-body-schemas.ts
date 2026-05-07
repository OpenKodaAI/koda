import type { z } from "zod";

type SchemaRoute = {
  method: "POST" | "PUT" | "PATCH";
  match: (segments: string[]) => boolean;
  schema: z.ZodType;
};

const registry: SchemaRoute[] = [];

/**
 * Register a body validation schema for a proxy route.
 * Called by domain-specific contract files at import time.
 */
export function registerBodySchema(route: SchemaRoute) {
  registry.push(route);
}

/**
 * Resolve a request method + path segments to the matching Zod schema.
 * Returns null if no schema is registered (body passes through unvalidated).
 */
export function resolveBodySchema(
  method: string,
  segments: string[],
): z.ZodType | null {
  for (const route of registry) {
    if (route.method === method && route.match(segments)) {
      return route.schema;
    }
  }
  return null;
}
