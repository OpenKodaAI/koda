import next from "next";
import { createDashboardServer } from "./src/lib/dashboard-server.mjs";
import { parseTrustedProxies } from "./src/lib/forwarded-for.mjs";
import { createRuntimeRelay, createUpgradeRouter } from "./src/lib/runtime-relay-server.mjs";

const dev = process.env.NODE_ENV !== "production";
const host = process.env.HOST ?? "0.0.0.0";
const port = Number.parseInt(process.env.PORT ?? "3000", 10);
const runtimeRelayStoreKey = Symbol.for("koda.web.runtime-relay-store");
// Peers whose x-forwarded-for is believed (loopback always). The dashboard
// server rewrites every request's header to the resolved client before
// Next.js sees it, so a client that reaches this port directly cannot choose
// its rate-limit bucket.
const trustedProxies = parseTrustedProxies(process.env.WEB_TRUSTED_PROXIES);

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

const app = next({ dev, hostname: host, port });
const handle = app.getRequestHandler();

await app.prepare();

// Next.js serves one upgrade here, the dev server's HMR socket: this app has
// no rewrites, so in production it would accept none.
const nextUpgrade = dev ? app.getUpgradeHandler() : null;

// Checks the relay descriptor and session cookie before the WebSocket
// handshake, and bounds frames in both directions (runtime-relay-server.mjs).
const runtimeRelay = createRuntimeRelay({ store: getRuntimeRelayStore() });

const server = createDashboardServer({
  handle,
  upgrade: createUpgradeRouter({ relay: runtimeRelay, nextUpgrade }),
  isTrusted: trustedProxies.isTrusted,
});

server.listen(port, host, () => {
  console.log(
    `> Runtime control plane server ready on http://${host}:${port} (${dev ? "dev" : "prod"})`
  );
  console.log(`> Trusting x-forwarded-for from ${trustedProxies.trusted.join(", ")}`);
  if (trustedProxies.ignored.length > 0) {
    console.warn(
      `> Ignoring WEB_TRUSTED_PROXIES entries (not an IP, a CIDR or an available gateway): ${trustedProxies.ignored.join(", ")}`
    );
  }
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
    runtimeRelay.closeAll(1001, "server_shutdown");
    setTimeout(() => process.exit(0), 2000).unref();
  });
}
