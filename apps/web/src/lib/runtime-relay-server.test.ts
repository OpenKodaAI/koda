// @vitest-environment node

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import http from "node:http";
import net, { type AddressInfo } from "node:net";
import { Duplex } from "node:stream";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WebSocket, WebSocketServer, type RawData } from "ws";
import { createDashboardServer } from "./dashboard-server.mjs";
import { isTrustedDashboardRequest } from "./request-origin";
import { createRuntimeRelayDescriptor, getRuntimeRelayPath } from "./runtime-relay";
import {
  RELAY_CLIENT_MAX_PAYLOAD_BYTES,
  RELAY_PATH_PREFIX,
  RELAY_UPSTREAM_MAX_PAYLOAD_BYTES,
  createRuntimeRelay,
  createUpgradeRouter,
} from "./runtime-relay-server.mjs";
import { buildClientWebSocketUrl } from "./runtime-ui";
import { sealWebOperatorToken } from "./web-operator-session";
import { WEB_OPERATOR_SESSION_COOKIE } from "./web-operator-session-constants";

type Descriptor = {
  upstreamUrl: string;
  upstreamHeaders?: Record<string, string>;
  expiresAt: string;
  tokenHash?: string;
};

type Upstream = {
  url: string;
  connections: number;
  messages: RawData[];
  headers: http.IncomingHttpHeaders[];
  sockets: WebSocket[];
};

const TOKEN = "operator-token";
// What rawUpgrade sends as Host, and the Origin of a dashboard page served there.
const DASHBOARD_HOST = "127.0.0.1";
const DASHBOARD_ORIGIN = `http://${DASHBOARD_HOST}`;
const tokenHash = (token: string) => createHash("sha256").update(token).digest("hex");
const inFiveMinutes = () => new Date(Date.now() + 5 * 60_000).toISOString();
// The Cookie header a browser sends once the login route has set the session
// cookie (setWebOperatorSessionCookie seals the token the same way).
const sessionCookie = (token: string) => `${WEB_OPERATOR_SESSION_COOKIE}=${sealWebOperatorToken(token)}`;

const closers: Array<() => Promise<void>> = [];

afterEach(async () => {
  await Promise.all(closers.splice(0).map((close) => close()));
  vi.unstubAllGlobals();
});

function listen(server: http.Server): Promise<number> {
  return new Promise((resolve) =>
    server.listen(0, "127.0.0.1", () => resolve((server.address() as AddressInfo).port)),
  );
}

function closeServer(server: http.Server): Promise<void> {
  return new Promise((resolve) => {
    server.closeAllConnections();
    server.close(() => resolve());
  });
}

// The runtime's WebSocket endpoint. Records everything that reaches it, which
// is how the tests tell whether the relay did any work.
async function startUpstream(): Promise<Upstream> {
  const server = http.createServer();
  const wss = new WebSocketServer({ server });
  const upstream: Upstream = { url: "", connections: 0, messages: [], headers: [], sockets: [] };
  wss.on("connection", (socket, request) => {
    upstream.connections += 1;
    upstream.headers.push(request.headers);
    upstream.sockets.push(socket);
    socket.on("message", (data) => upstream.messages.push(data));
  });
  const port = await listen(server);
  upstream.url = `ws://127.0.0.1:${port}/ws/runtime/tasks/1/terminals/1`;
  closers.push(async () => {
    wss.clients.forEach((client) => client.terminate());
    await new Promise<void>((resolve) => wss.close(() => resolve()));
    await closeServer(server);
  });
  return upstream;
}

type NextUpgrade = (request: http.IncomingMessage, socket: Duplex, head: Buffer) => unknown;

// The dashboard as server.mjs assembles it: the dashboard server hands every
// upgrade to the upgrade router, which routes relay paths to the relay. Next.js
// is not here: `nextUpgrade` stands in for its dev upgrade handler.
async function startDashboard(
  descriptors: Map<string, Descriptor>,
  nextUpgrade: NextUpgrade | null = null,
): Promise<number> {
  const relay = createRuntimeRelay({ store: { descriptors } });
  const server = createDashboardServer({
    handle: (_request, response) => {
      response.writeHead(404);
      response.end();
    },
    upgrade: createUpgradeRouter({ relay, nextUpgrade }),
    isTrusted: () => false,
  });
  const port = await listen(server);
  closers.push(async () => {
    relay.closeAll(1001, "test_shutdown");
    await closeServer(server);
  });
  return port;
}

type UpgradeTarget = { host?: string; origin?: string | null };

// The request head of a WebSocket upgrade. A browser always sends Origin, the
// page's origin; `origin: null` leaves it out.
function upgradeRequest(
  path: string,
  headers: string[],
  { host = DASHBOARD_HOST, origin = DASHBOARD_ORIGIN }: UpgradeTarget,
): string {
  return [
    `GET ${path} HTTP/1.1`,
    `Host: ${host}`,
    "Connection: Upgrade",
    "Upgrade: websocket",
    "Sec-WebSocket-Version: 13",
    "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
    ...(origin === null ? [] : [`Origin: ${origin}`]),
    ...headers,
    "",
    "",
  ].join("\r\n");
}

// Sends a WebSocket upgrade by hand and returns the raw response head, so a
// refusal can be told apart from a completed handshake.
function rawUpgrade(
  port: number,
  path: string,
  headers: string[] = [],
  target: UpgradeTarget = {},
): Promise<{ status: number; head: string; socket: net.Socket }> {
  return new Promise((resolve, reject) => {
    const socket = net.connect(port, "127.0.0.1", () => {
      socket.write(upgradeRequest(path, headers, target));
    });
    let text = "";
    const onData = (chunk: Buffer) => {
      text += chunk.toString("latin1");
      const end = text.indexOf("\r\n\r\n");
      if (end === -1) return;
      socket.off("data", onData);
      const head = text.slice(0, end);
      resolve({ status: Number(head.split(" ")[1]), head, socket });
    };
    socket.on("data", onData);
    socket.on("error", reject);
    closers.push(async () => {
      socket.destroy();
    });
  });
}

// A client that sends an upgrade and resets the connection at once, as a
// browser that aborts mid-handshake does.
function upgradeThenReset(port: number, path: string, headers: string[] = []): Promise<void> {
  return new Promise((resolve) => {
    const socket = net.connect(port, "127.0.0.1", () => {
      socket.write(upgradeRequest(path, headers, {}), () => socket.resetAndDestroy());
    });
    socket.on("error", () => undefined);
    socket.on("close", () => resolve());
  });
}

function waitForClose(socket: net.Socket): Promise<void> {
  return new Promise((resolve) => {
    if (socket.destroyed) resolve();
    else socket.once("close", () => resolve());
  });
}

// Reads one server-to-client frame (never masked) from a raw socket.
function readFrame(socket: net.Socket): Promise<{ opcode: number; payload: Buffer }> {
  return new Promise((resolve, reject) => {
    let buffer = Buffer.alloc(0);
    const onData = (chunk: Buffer) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (buffer.length < 2) return;
      let length = buffer[1] & 0x7f;
      let offset = 2;
      if (length === 126) {
        if (buffer.length < 4) return;
        length = buffer.readUInt16BE(2);
        offset = 4;
      }
      if (buffer.length < offset + length) return;
      socket.off("data", onData);
      resolve({ opcode: buffer[0] & 0x0f, payload: buffer.subarray(offset, offset + length) });
    };
    socket.on("data", onData);
    socket.once("error", reject);
  });
}

// A browser's WebSocket: it sends the session cookie and the page's origin.
function connectClient(url: string, cookie: string, origin: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const client = new WebSocket(url, { headers: { Cookie: cookie }, origin, perMessageDeflate: false });
    client.once("open", () => resolve(client));
    client.once("error", reject);
    closers.push(async () => {
      client.terminate();
    });
  });
}

function waitFor(predicate: () => boolean, timeoutMs = 5_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (predicate()) resolve();
      else if (Date.now() > deadline) reject(new Error("condition not met in time"));
      else setTimeout(tick, 10);
    };
    tick();
  });
}

function closeEvent(client: WebSocket): Promise<{ code: number; reason: string }> {
  return new Promise((resolve) =>
    client.once("close", (code, reason) => resolve({ code, reason: reason.toString() })),
  );
}

async function authorizedRelay(extra: Partial<Descriptor> = {}) {
  const upstream = await startUpstream();
  const descriptors = new Map<string, Descriptor>([
    [
      "relay-1",
      {
        upstreamUrl: upstream.url,
        upstreamHeaders: { "X-Koda-Attach-Token": "attach-secret" },
        expiresAt: inFiveMinutes(),
        tokenHash: tokenHash(TOKEN),
        ...extra,
      },
    ],
  ]);
  const port = await startDashboard(descriptors);
  const path = `${RELAY_PATH_PREFIX}relay-1`;
  return {
    upstream,
    descriptors,
    port,
    path,
    connect: () => connectClient(`ws://127.0.0.1:${port}${path}`, sessionCookie(TOKEN), `http://127.0.0.1:${port}`),
  };
}

const RELAY_STORE_KEY = Symbol.for("koda.web.runtime-relay-store");

// The store the attach route writes to (runtime-relay.ts) and server.mjs reads.
function sharedRelayStore(): { descriptors: Map<string, Descriptor> } {
  return (globalThis as Record<symbol, { descriptors: Map<string, Descriptor> }>)[RELAY_STORE_KEY];
}

describe("runtime relay upgrade", () => {
  it("admits the browser that attached: relay_path as the attach route returns it, the session cookie, no token in the URL", async () => {
    const upstream = await startUpstream();
    // What POST .../terminal/attach does with the operator token it unsealed from the cookie.
    const relay = await createRuntimeRelayDescriptor(
      {
        kind: "terminal",
        agentId: "ATLAS",
        taskId: 1,
        upstreamUrl: upstream.url,
        upstreamHeaders: { "X-Koda-Attach-Token": "attach-secret" },
        expiresAt: inFiveMinutes(),
      },
      TOKEN,
    );
    closers.push(async () => {
      sharedRelayStore().descriptors.delete(relay.id);
    });
    const port = await startDashboard(sharedRelayStore().descriptors);
    // What the terminal panel does: buildClientWebSocketUrl(relay_path), and the
    // browser adds the session cookie.
    vi.stubGlobal("window", { location: { origin: `http://127.0.0.1:${port}` } });
    const url = buildClientWebSocketUrl(getRuntimeRelayPath(relay.id));
    expect(new URL(url).search).toBe("");

    const client = await connectClient(url, sessionCookie(TOKEN), window.location.origin);
    await waitFor(() => upstream.sockets[0]?.readyState === WebSocket.OPEN);
    expect(upstream.headers[0]["x-koda-attach-token"]).toBe("attach-secret");
    client.send(JSON.stringify({ type: "input", data: "ls\n" }));
    await waitFor(() => upstream.messages.length === 1);
    expect(upstream.messages[0].toString()).toBe('{"type":"input","data":"ls\\n"}');
  });

  it("refuses an unknown relay with 404 before the handshake and never contacts the runtime", async () => {
    const { upstream, port } = await authorizedRelay();

    for (const path of [`${RELAY_PATH_PREFIX}unknown`, RELAY_PATH_PREFIX]) {
      const response = await rawUpgrade(port, path, [`Cookie: ${sessionCookie(TOKEN)}`]);
      expect(response.status).toBe(404);
      expect(response.head).not.toMatch(/sec-websocket-accept/i);
      await waitForClose(response.socket);
    }
    expect(upstream.connections).toBe(0);
  });

  it("refuses an upgrade without the session cookie, or with another session's, with 401 before the handshake", async () => {
    const { upstream, port, path } = await authorizedRelay();

    const cookies = [
      [],
      [`Cookie: other=1`],
      [`Cookie: ${WEB_OPERATOR_SESSION_COOKIE}=`],
      [`Cookie: ${sessionCookie("another-operator")}`],
      // Not sealed: the raw token, and a sealed value that was tampered with.
      [`Cookie: ${WEB_OPERATOR_SESSION_COOKIE}=${TOKEN}`],
      [`Cookie: ${sessionCookie(TOKEN).slice(0, -2)}xx`],
    ];
    for (const headers of cookies) {
      const response = await rawUpgrade(port, path, headers);
      expect(response.status, headers.join()).toBe(401);
      expect(response.head).not.toMatch(/sec-websocket-accept/i);
      await waitForClose(response.socket);
    }
    expect(upstream.connections).toBe(0);
  });

  it("does not take the session token from the URL, where it would reach access logs", async () => {
    const { upstream, port, path } = await authorizedRelay();

    for (const query of [`?token=${TOKEN}`, `?token=${encodeURIComponent(sealWebOperatorToken(TOKEN))}`]) {
      const response = await rawUpgrade(port, `${path}${query}`);
      expect(response.status, query).toBe(401);
    }
    expect(upstream.connections).toBe(0);
  });

  it("refuses an upgrade from another origin with 403 before any relay work, even with the session cookie", async () => {
    const { upstream, port, path } = await authorizedRelay();

    // A browser attaches the SameSite=Strict cookie for a same-site page:
    // another port on the same host, a sibling subdomain. Another scheme, the
    // "null" a sandboxed page sends, and no Origin at all (only non-browser
    // clients leave it out) are refused too.
    const origins = [
      null,
      "null",
      "http://127.0.0.1:8080",
      "http://app.127.0.0.1",
      "https://127.0.0.1",
      "http://127.0.0.1.evil.example",
      "",
    ];
    for (const relayPath of [path, `${RELAY_PATH_PREFIX}unknown`]) {
      for (const origin of origins) {
        const response = await rawUpgrade(port, relayPath, [`Cookie: ${sessionCookie(TOKEN)}`], { origin });
        expect(response.status, `${relayPath} ${origin}`).toBe(403);
        expect(response.head).not.toMatch(/sec-websocket-accept/i);
        await waitForClose(response.socket);
      }
    }
    expect(upstream.connections).toBe(0);
  });

  it("takes only the Origin: not the Referer or Sec-Fetch-Site that request-origin.ts also admits", async () => {
    const { upstream, port, path } = await authorizedRelay();
    const fallbacks = [`Referer: ${DASHBOARD_ORIGIN}/sessions`, "Sec-Fetch-Site: same-origin"];

    for (const origin of [null, "http://127.0.0.1:8080"]) {
      for (const fallback of fallbacks) {
        const [name, value] = fallback.split(": ");
        // The dashboard's other routes admit such a change (request-origin.ts).
        const headers = new Headers({ host: DASHBOARD_HOST, [name]: value });
        if (origin !== null) headers.set("origin", origin);
        const change = { method: "POST", headers };
        expect(isTrustedDashboardRequest(change), `${origin} ${fallback}`).toBe(true);

        const response = await rawUpgrade(port, path, [`Cookie: ${sessionCookie(TOKEN)}`, fallback], { origin });
        expect(response.status, `${origin} ${fallback}`).toBe(403);
        await waitForClose(response.socket);
      }
    }
    expect(upstream.connections).toBe(0);
  });

  it("takes the dashboard origin from Host and X-Forwarded-Proto, as a TLS-terminating proxy sends them", async () => {
    const { upstream, port, path } = await authorizedRelay();
    const cookie = `Cookie: ${sessionCookie(TOKEN)}`;
    const host = "koda.example.com";

    // Traefik sends wss for a WebSocket it received over TLS, nginx and Caddy https.
    for (const proto of ["https", "wss", "https, http"]) {
      const response = await rawUpgrade(port, path, [cookie, `X-Forwarded-Proto: ${proto}`], {
        host,
        origin: `https://${host}`,
      });
      expect(response.status, proto).toBe(101);
    }
    await waitFor(() => upstream.connections === 3);

    const refused = [
      { proto: "https", origin: `http://${host}` },
      { proto: "http", origin: `https://${host}` },
      { proto: "https", origin: `https://other.example.com` },
    ];
    for (const { proto, origin } of refused) {
      const response = await rawUpgrade(port, path, [cookie, `X-Forwarded-Proto: ${proto}`], { host, origin });
      expect(response.status, `${proto} ${origin}`).toBe(403);
    }
    expect(upstream.connections).toBe(3);
  });

  it("refuses a relay that was stored without a token hash instead of letting anyone in", async () => {
    const { upstream, port, path } = await authorizedRelay({ tokenHash: undefined });

    const response = await rawUpgrade(port, path, [`Cookie: ${sessionCookie(TOKEN)}`]);
    expect(response.status).toBe(401);
    expect(upstream.connections).toBe(0);
  });

  it("refuses an expired relay with 404 and forgets it", async () => {
    const { upstream, descriptors, port, path } = await authorizedRelay({
      expiresAt: new Date(Date.now() - 1_000).toISOString(),
    });

    const response = await rawUpgrade(port, path, [`Cookie: ${sessionCookie(TOKEN)}`]);
    expect(response.status).toBe(404);
    expect(descriptors.has("relay-1")).toBe(false);
    expect(upstream.connections).toBe(0);
  });

  it("relays both directions once the descriptor and session cookie check out", async () => {
    const { upstream, connect } = await authorizedRelay();

    const client = await connect();
    await waitFor(() => upstream.sockets.length === 1 && upstream.sockets[0].readyState === WebSocket.OPEN);
    expect(upstream.headers[0]["x-koda-attach-token"]).toBe("attach-secret");

    const received: string[] = [];
    client.on("message", (data) => received.push(data.toString()));
    upstream.sockets[0].send("from-runtime");
    await waitFor(() => received.length === 1);
    expect(received).toEqual(["from-runtime"]);

    client.send(JSON.stringify({ type: "input", data: "ls\n" }));
    await waitFor(() => upstream.messages.length === 1);
    expect(upstream.messages[0].toString()).toBe('{"type":"input","data":"ls\\n"}');
  });
});

describe("dashboard upgrade routing", () => {
  it("answers 404 at once to an upgrade that is neither the relay nor Next.js's, instead of leaving it open", async () => {
    const nextUpgrades: string[] = [];
    const port = await startDashboard(new Map(), (request) => {
      nextUpgrades.push(String(request.url));
    });

    for (const path of ["/anything", "/api/runtime/agents/ATLAS/tasks/1/terminal", "/api/runtime/relay"]) {
      const response = await rawUpgrade(port, path);
      expect(response.status, path).toBe(404);
      await waitForClose(response.socket);
    }
    expect(nextUpgrades).toEqual([]);
  });

  it("hands /_next/ upgrades (the dev HMR socket) to Next.js when server.mjs passes its handler", async () => {
    const nextUpgrades: string[] = [];
    const port = await startDashboard(new Map(), (request, socket) => {
      nextUpgrades.push(String(request.url));
      socket.end("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n");
    });

    const response = await rawUpgrade(port, "/_next/hmr?id=1");
    expect(response.status).toBe(101);
    expect(nextUpgrades).toEqual(["/_next/hmr?id=1"]);
  });

  it("refuses /_next/ upgrades with 404 when there is no Next.js handler (production)", async () => {
    const port = await startDashboard(new Map(), null);

    const response = await rawUpgrade(port, "/_next/hmr");
    expect(response.status).toBe(404);
    await waitForClose(response.socket);
  });
});

describe("refused upgrades and connection resets", () => {
  it("survives clients that reset the connection while a refusal is written", async () => {
    const uncaught = vi.fn();
    process.on("uncaughtException", uncaught);
    closers.push(async () => {
      process.off("uncaughtException", uncaught);
    });
    const { upstream, port, path } = await authorizedRelay();

    const resets: Promise<void>[] = [];
    for (let attempt = 0; attempt < 50; attempt += 1) {
      resets.push(upgradeThenReset(port, path)); // 401
      resets.push(upgradeThenReset(port, `${RELAY_PATH_PREFIX}unknown`)); // 404
      resets.push(upgradeThenReset(port, "/anything")); // 404, unrouted
    }
    await Promise.all(resets);
    // The server is still up and still refuses.
    const response = await rawUpgrade(port, "/anything");
    expect(response.status).toBe(404);
    await waitForClose(response.socket);

    expect(uncaught).not.toHaveBeenCalled();
    expect(upstream.connections).toBe(0);
  });

  it("destroys the socket instead of raising when writing the refusal fails", async () => {
    const uncaught = vi.fn();
    process.on("uncaughtException", uncaught);
    closers.push(async () => {
      process.off("uncaughtException", uncaught);
    });
    const relay = createRuntimeRelay({ store: { descriptors: new Map() } });
    // Stands in for Node's http server, which removes its own error listener
    // from the socket before it emits "upgrade".
    const route = createUpgradeRouter({ relay });

    for (const url of ["/anything", `${RELAY_PATH_PREFIX}unknown`]) {
      const socket = new Duplex({
        read() {},
        write(_chunk, _encoding, callback) {
          callback(Object.assign(new Error("write ECONNRESET"), { code: "ECONNRESET" }));
        },
      });
      route({ url, headers: { host: DASHBOARD_HOST, origin: DASHBOARD_ORIGIN } } as http.IncomingMessage, socket, Buffer.alloc(0));
      await waitFor(() => socket.destroyed);
      // The stream emits the write error on the next tick.
      await new Promise((resolve) => setImmediate(resolve));
      expect(uncaught, url).not.toHaveBeenCalled();
    }
  });
});

describe("runtime relay frame limits", () => {
  it("bounds frames in both directions at 4 MiB, the runtime's own inbound limit", () => {
    expect(RELAY_CLIENT_MAX_PAYLOAD_BYTES).toBe(4 * 1024 * 1024);
    expect(RELAY_UPSTREAM_MAX_PAYLOAD_BYTES).toBe(4 * 1024 * 1024);
  });

  it("relays a client frame at the limit (a 4 MiB terminal paste) and closes with 1009 on one byte more, without relaying it", async () => {
    const { upstream, connect } = await authorizedRelay();
    const client = await connect();
    await waitFor(() => upstream.sockets[0]?.readyState === WebSocket.OPEN);

    client.send(Buffer.alloc(RELAY_CLIENT_MAX_PAYLOAD_BYTES, 1));
    await waitFor(() => upstream.messages.length === 1);
    expect((upstream.messages[0] as Buffer).length).toBe(RELAY_CLIENT_MAX_PAYLOAD_BYTES);

    const closed = closeEvent(client);
    client.send(Buffer.alloc(RELAY_CLIENT_MAX_PAYLOAD_BYTES + 1, 2));
    expect((await closed).code).toBe(1009);
    await waitFor(() => upstream.sockets[0].readyState === WebSocket.CLOSED);
    expect(upstream.messages).toHaveLength(1);
  });

  it("closes with 1009 on the frame header alone, before any of an oversized payload arrives", async () => {
    const { upstream, port, path } = await authorizedRelay();
    const response = await rawUpgrade(port, path, [`Cookie: ${sessionCookie(TOKEN)}`]);
    expect(response.status).toBe(101);
    await waitFor(() => upstream.sockets[0]?.readyState === WebSocket.OPEN);

    // A masked binary frame header that announces one byte over the limit
    // (far below ws's 100 MiB default) and sends no payload.
    const header = Buffer.alloc(14);
    header[0] = 0x82;
    header[1] = 0x80 | 127;
    header.writeBigUInt64BE(BigInt(RELAY_CLIENT_MAX_PAYLOAD_BYTES + 1), 2);
    header.writeUInt32BE(0x01020304, 10);
    const frame = readFrame(response.socket);
    response.socket.write(header);

    const close = await frame;
    expect(close.opcode).toBe(0x8);
    expect(close.payload.readUInt16BE(0)).toBe(1009);
    expect(upstream.messages).toHaveLength(0);
  });

  it("closes the client instead of relaying a runtime frame over the limit", async () => {
    const { upstream, connect } = await authorizedRelay();
    const client = await connect();
    await waitFor(() => upstream.sockets[0]?.readyState === WebSocket.OPEN);

    const received: RawData[] = [];
    client.on("message", (data) => received.push(data));
    const closed = closeEvent(client);
    upstream.sockets[0].send(Buffer.alloc(RELAY_UPSTREAM_MAX_PAYLOAD_BYTES + 1, 3));

    expect(await closed).toEqual({ code: 1011, reason: "upstream_error" });
    expect(received).toHaveLength(0);
  });
});

describe("server.mjs relay wiring", () => {
  it("routes upgrades through createUpgradeRouter and opens no WebSocket of its own", async () => {
    const source = await readFile(new URL("../../server.mjs", import.meta.url), "utf8");

    expect(source).toMatch(/\bcreateRuntimeRelay\(\{ store: getRuntimeRelayStore\(\) \}\)/);
    expect(source).toMatch(/\bupgrade: createUpgradeRouter\(\{ relay: runtimeRelay, nextUpgrade \}\)/);
    // Only the dev server's HMR socket goes to Next.js.
    expect(source).toMatch(/const nextUpgrade = dev \? app\.getUpgradeHandler\(\) : null;/);
    expect(source).not.toMatch(/from "ws"/);
    expect(source).not.toMatch(/\bWebSocketServer\b|new WebSocket\(/);
  });

  it("reads the request target only through parseRequestUrl, and the Host header only to compare it with Origin", async () => {
    const source = await readFile(new URL("./runtime-relay-server.mjs", import.meta.url), "utf8");

    // Nothing the client sends is parsed as a URL: a `new URL` that throws in
    // an upgrade listener would stop the process.
    expect(source).not.toMatch(/new URL\(/);
    expect(source.match(/\bparseRequestUrl\(request\)/g)).toHaveLength(1);
    expect(source.match(/headers\.host\b/g)).toHaveLength(1);
  });
});
