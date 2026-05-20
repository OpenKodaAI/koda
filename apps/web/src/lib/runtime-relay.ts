import crypto from "node:crypto";
import { ValidationError } from "@/lib/errors";

export interface RuntimeRelayDescriptor {
  id: string;
  kind: "terminal" | "browser" | "novnc";
  agentId: string;
  taskId: number;
  upstreamUrl: string;
  upstreamHeaders?: Record<string, string>;
  createdAt: string;
  expiresAt: string;
  terminalId?: number | null;
  tokenHash?: string;
}

interface RuntimeRelayStore {
  descriptors: Map<string, RuntimeRelayDescriptor>;
}

const RUNTIME_RELAY_STORE_KEY = Symbol.for("koda.web.runtime-relay-store");

function getRuntimeRelayStore() {
  const scope = globalThis as typeof globalThis & {
    [RUNTIME_RELAY_STORE_KEY]?: RuntimeRelayStore;
  };

  if (!scope[RUNTIME_RELAY_STORE_KEY]) {
    scope[RUNTIME_RELAY_STORE_KEY] = {
      descriptors: new Map<string, RuntimeRelayDescriptor>(),
    };
  }

  return scope[RUNTIME_RELAY_STORE_KEY]!;
}

function isExpired(descriptor: Partial<RuntimeRelayDescriptor>) {
  const expiresAt = Date.parse(String(descriptor.expiresAt || ""));
  return !Number.isFinite(expiresAt) || expiresAt <= Date.now();
}

export async function cleanupExpiredRuntimeRelayDescriptors() {
  const store = getRuntimeRelayStore();

  for (const [id, descriptor] of store.descriptors.entries()) {
    if (isExpired(descriptor)) {
      store.descriptors.delete(id);
    }
  }
}

export async function createRuntimeRelayDescriptor(
  descriptor: Omit<RuntimeRelayDescriptor, "id" | "createdAt" | "tokenHash">,
  sessionToken?: string,
) {
  await cleanupExpiredRuntimeRelayDescriptors();
  const store = getRuntimeRelayStore();
  const tokenHash = sessionToken
    ? crypto.createHash("sha256").update(sessionToken).digest("hex")
    : undefined;
  const payload: RuntimeRelayDescriptor = {
    ...descriptor,
    id: crypto.randomBytes(18).toString("hex"),
    createdAt: new Date().toISOString(),
    ...(tokenHash ? { tokenHash } : {}),
  };
  store.descriptors.set(payload.id, payload);
  return payload;
}

export async function readRuntimeRelayDescriptor(relayId: string) {
  await cleanupExpiredRuntimeRelayDescriptors();
  const store = getRuntimeRelayStore();
  const descriptor = store.descriptors.get(relayId) ?? null;
  if (!descriptor) return null;
  if (isExpired(descriptor)) {
    store.descriptors.delete(relayId);
    return null;
  }
  return descriptor;
}

export function getRuntimeRelayPath(relayId: string) {
  return `/api/runtime/relay/${relayId}`;
}

export function toAbsoluteUpstreamWsUrl(baseUrl: string, wsPathOrUrl: string) {
  const resolved = /^wss?:\/\//i.test(wsPathOrUrl)
    ? new URL(wsPathOrUrl)
    : (() => {
        const base = new URL(baseUrl);
        base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
        return new URL(wsPathOrUrl, base);
      })();

  if (!["ws:", "wss:"].includes(resolved.protocol)) {
    throw new ValidationError("Invalid relay websocket URL.");
  }

  return resolved.toString();
}
