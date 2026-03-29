import crypto from "node:crypto";
import { ValidationError } from "@/lib/errors";

export interface RuntimeRelayDescriptor {
  id: string;
  kind: "terminal" | "browser" | "novnc";
  botId: string;
  taskId: number;
  upstreamUrl: string;
  createdAt: string;
  expiresAt: string;
  terminalId?: number | null;
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
  descriptor: Omit<RuntimeRelayDescriptor, "id" | "createdAt">
) {
  await cleanupExpiredRuntimeRelayDescriptors();
  const store = getRuntimeRelayStore();
  const payload: RuntimeRelayDescriptor = {
    ...descriptor,
    id: crypto.randomBytes(18).toString("hex"),
    createdAt: new Date().toISOString(),
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
