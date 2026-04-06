import http from "node:http";
import next from "next";
import { WebSocket, WebSocketServer } from "ws";

const dev = process.env.NODE_ENV !== "production";
const host = process.env.HOST ?? "0.0.0.0";
const port = Number.parseInt(process.env.PORT ?? "3000", 10);
const relayPathPrefix = "/api/runtime/relay/";
const runtimeRelayStoreKey = Symbol.for("koda.web.runtime-relay-store");

function getRuntimeRelayStore() {
  if (!globalThis[runtimeRelayStoreKey]) {
    globalThis[runtimeRelayStoreKey] = {
      descriptors: new Map(),
    };

    setInterval(() => {
      const store = globalThis[runtimeRelayStoreKey];
      const now = Date.now();
      for (const [relayId, descriptor] of store.descriptors.entries()) {
        const expiresAt = Date.parse(String(descriptor.expiresAt || ""));
        if (!Number.isFinite(expiresAt) || expiresAt <= now) {
          store.descriptors.delete(relayId);
        }
      }
    }, 60_000).unref();
  }

  return globalThis[runtimeRelayStoreKey];
}

function readRelayDescriptor(relayId) {
  const store = getRuntimeRelayStore();
  const descriptor = store.descriptors.get(relayId) ?? null;
  if (!descriptor) return null;

  const expiresAt = Date.parse(String(descriptor.expiresAt || ""));
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
    store.descriptors.delete(relayId);
    return null;
  }

  return descriptor;
}

function closeSocket(socket, code, reason) {
  if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
    socket.close(code, reason);
  }
}

async function handleRelayConnection(client, request) {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
  const relayId = url.pathname.slice(relayPathPrefix.length);
  const descriptor = readRelayDescriptor(relayId);

  if (!descriptor?.upstreamUrl) {
    closeSocket(client, 4404, "relay_not_found");
    return;
  }

  // Validate session token from query parameter (timing-safe comparison)
  const clientToken = url.searchParams.get('token');
  if (descriptor.tokenHash && clientToken) {
    const crypto = await import('node:crypto');
    const hash = crypto.createHash('sha256').update(clientToken).digest('hex');
    const hashBuf = Buffer.from(hash, 'hex');
    const expectedBuf = Buffer.from(descriptor.tokenHash, 'hex');
    if (hashBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(hashBuf, expectedBuf)) {
      closeSocket(client, 4401, "unauthorized");
      return;
    }
  } else if (descriptor.tokenHash && !clientToken) {
    closeSocket(client, 4401, "unauthorized");
    return;
  }

  const upstream = new WebSocket(String(descriptor.upstreamUrl), {
    headers:
      descriptor.upstreamHeaders && typeof descriptor.upstreamHeaders === "object"
        ? descriptor.upstreamHeaders
        : undefined,
    perMessageDeflate: false,
  });

  upstream.on("message", (data, isBinary) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(data, { binary: isBinary });
    }
  });

  client.on("message", (data, isBinary) => {
    if (upstream.readyState === WebSocket.OPEN) {
      upstream.send(data, { binary: isBinary });
    }
  });

  upstream.on("close", (code, reason) => {
    closeSocket(client, code || 1000, reason.toString() || "upstream_closed");
  });

  client.on("close", () => {
    closeSocket(upstream, 1000, "client_closed");
  });

  upstream.on("error", () => {
    closeSocket(client, 1011, "upstream_error");
  });

  client.on("error", () => {
    closeSocket(upstream, 1011, "client_error");
  });
}

const app = next({ dev, hostname: host, port });
const handle = app.getRequestHandler();

await app.prepare();

const upgradeHandler =
  typeof app.getUpgradeHandler === "function"
    ? app.getUpgradeHandler()
    : null;

const relayWss = new WebSocketServer({ noServer: true });
relayWss.on("connection", (client, request) => {
  void handleRelayConnection(client, request);
});

const server = http.createServer((request, response) => {
  void handle(request, response);
});

server.on("upgrade", (request, socket, head) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);

  if (url.pathname.startsWith(relayPathPrefix)) {
    relayWss.handleUpgrade(request, socket, head, (client) => {
      relayWss.emit("connection", client, request);
    });
    return;
  }

  if (upgradeHandler) {
    upgradeHandler(request, socket, head);
    return;
  }

  socket.destroy();
});

server.listen(port, host, () => {
  console.log(
    `> Runtime control plane server ready on http://${host}:${port} (${dev ? "dev" : "prod"})`
  );
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
    relayWss.clients.forEach((client) => closeSocket(client, 1001, "server_shutdown"));
    setTimeout(() => process.exit(0), 2000).unref();
  });
}
