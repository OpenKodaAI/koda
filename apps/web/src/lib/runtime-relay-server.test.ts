// @vitest-environment node

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import http from "node:http";
import net, { type AddressInfo } from "node:net";
import type { Duplex } from "node:stream";
import { afterEach, describe, expect, it } from "vitest";
import { WebSocket, WebSocketServer, type RawData } from "ws";
import { createDashboardServer, parseRequestUrl } from "./dashboard-server.mjs";
import {
  RELAY_CLIENT_MAX_PAYLOAD_BYTES,
  RELAY_PATH_PREFIX,
  RELAY_UPSTREAM_MAX_PAYLOAD_BYTES,
  createRuntimeRelay,
} from "./runtime-relay-server.mjs";

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
const tokenHash = (token: string) => createHash("sha256").update(token).digest("hex");
const inFiveMinutes = () => new Date(Date.now() + 5 * 60_000).toISOString();

const closers: Array<() => Promise<void>> = [];

afterEach(async () => {
  await Promise.all(closers.splice(0).map((close) => close()));
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

// The dashboard as server.mjs assembles it: the dashboard server routes
// relay-path upgrades to the relay and refuses the rest (Next.js is not here).
async function startDashboard(descriptors: Map<string, Descriptor>): Promise<number> {
  const relay = createRuntimeRelay({ store: { descriptors } });
  const server = createDashboardServer({
    handle: (_request, response) => {
      response.writeHead(404);
      response.end();
    },
    upgrade: (request: http.IncomingMessage, socket: Duplex, head: Buffer) => {
      const url = parseRequestUrl(request);
      if (url?.pathname.startsWith(RELAY_PATH_PREFIX)) {
        relay.handleUpgrade(request, socket, head, url);
        return;
      }
      socket.destroy();
    },
    isTrusted: () => false,
  });
  const port = await listen(server);
  closers.push(async () => {
    relay.closeAll(1001, "test_shutdown");
    await closeServer(server);
  });
  return port;
}

// Sends a WebSocket upgrade by hand and returns the raw response head, so a
// refusal can be told apart from a completed handshake.
function rawUpgrade(port: number, path: string): Promise<{ status: number; head: string; socket: net.Socket }> {
  return new Promise((resolve, reject) => {
    const socket = net.connect(port, "127.0.0.1", () => {
      socket.write(
        [
          `GET ${path} HTTP/1.1`,
          "Host: 127.0.0.1",
          "Connection: Upgrade",
          "Upgrade: websocket",
          "Sec-WebSocket-Version: 13",
          "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
          "",
          "",
        ].join("\r\n"),
      );
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

function connectClient(port: number, path: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const client = new WebSocket(`ws://127.0.0.1:${port}${path}`, { perMessageDeflate: false });
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
  return { upstream, descriptors, port, path: `${RELAY_PATH_PREFIX}relay-1?token=${TOKEN}` };
}

describe("runtime relay upgrade", () => {
  it("refuses an unknown relay with 404 before the handshake and never contacts the runtime", async () => {
    const { upstream, port } = await authorizedRelay();

    for (const path of [`${RELAY_PATH_PREFIX}unknown?token=${TOKEN}`, RELAY_PATH_PREFIX]) {
      const response = await rawUpgrade(port, path);
      expect(response.status).toBe(404);
      expect(response.head).not.toMatch(/sec-websocket-accept/i);
      await waitForClose(response.socket);
    }
    expect(upstream.connections).toBe(0);
  });

  it("refuses an upgrade without the session token, or with a wrong one, with 401 before the handshake", async () => {
    const { upstream, port } = await authorizedRelay();

    for (const query of ["", "?token=", "?token=wrong-token", `?token=${TOKEN}x`, `?other=${TOKEN}`]) {
      const response = await rawUpgrade(port, `${RELAY_PATH_PREFIX}relay-1${query}`);
      expect(response.status, query).toBe(401);
      expect(response.head).not.toMatch(/sec-websocket-accept/i);
      await waitForClose(response.socket);
    }
    expect(upstream.connections).toBe(0);
  });

  it("refuses a relay that was stored without a token hash instead of letting anyone in", async () => {
    const { upstream, port } = await authorizedRelay({ tokenHash: undefined });

    for (const query of ["", `?token=${TOKEN}`]) {
      const response = await rawUpgrade(port, `${RELAY_PATH_PREFIX}relay-1${query}`);
      expect(response.status, query).toBe(401);
    }
    expect(upstream.connections).toBe(0);
  });

  it("refuses an expired relay with 404 and forgets it", async () => {
    const { upstream, descriptors, port, path } = await authorizedRelay({
      expiresAt: new Date(Date.now() - 1_000).toISOString(),
    });

    const response = await rawUpgrade(port, path);
    expect(response.status).toBe(404);
    expect(descriptors.has("relay-1")).toBe(false);
    expect(upstream.connections).toBe(0);
  });

  it("relays both directions once the descriptor and token check out", async () => {
    const { upstream, port, path } = await authorizedRelay();

    const client = await connectClient(port, path);
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

describe("runtime relay frame limits", () => {
  it("bounds client frames at 1 MiB and runtime frames at 4 MiB", () => {
    expect(RELAY_CLIENT_MAX_PAYLOAD_BYTES).toBe(1024 * 1024);
    expect(RELAY_UPSTREAM_MAX_PAYLOAD_BYTES).toBe(4 * 1024 * 1024);
  });

  it("relays a client frame at the limit and closes with 1009 on one byte more, without relaying it", async () => {
    const { upstream, port, path } = await authorizedRelay();
    const client = await connectClient(port, path);
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
    const response = await rawUpgrade(port, path);
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
    const { upstream, port, path } = await authorizedRelay();
    const client = await connectClient(port, path);
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
  it("routes relay upgrades through createRuntimeRelay and opens no WebSocket of its own", async () => {
    const source = await readFile(new URL("../../server.mjs", import.meta.url), "utf8");

    expect(source).toMatch(/\bcreateRuntimeRelay\(\{ store: getRuntimeRelayStore\(\) \}\)/);
    expect(source).toMatch(/url\.pathname\.startsWith\(RELAY_PATH_PREFIX\)/);
    expect(source).toMatch(/\bruntimeRelay\.handleUpgrade\(request, socket, head, url\)/);
    expect(source).not.toMatch(/from "ws"/);
    expect(source).not.toMatch(/\bWebSocketServer\b|new WebSocket\(/);
  });

  it("reads the request target only from the URL server.mjs parsed, never the Host header", async () => {
    const source = await readFile(new URL("./runtime-relay-server.mjs", import.meta.url), "utf8");

    expect(source).not.toMatch(/new URL\(/);
    expect(source).not.toMatch(/headers\.host/);
  });
});
