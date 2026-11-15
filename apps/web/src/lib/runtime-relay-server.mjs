/**
 * The runtime relay: a WebSocket at `/api/runtime/relay/<id>` that the
 * dashboard bridges to a worker's terminal, browser snapshot or noVNC socket.
 * server.mjs hands every upgrade to `createUpgradeRouter`, which routes
 * relay-path upgrades here. The Origin, the relay descriptor (written by
 * `runtime-relay.ts` when an operator attaches) and the session cookie are
 * checked before the WebSocket handshake, so a request that is not authorised
 * gets a plain HTTP refusal: no WebSocket, no frame parsing and no upstream
 * connection.
 */

import { createHash, timingSafeEqual } from "node:crypto";
import { STATUS_CODES } from "node:http";
import { WebSocket, WebSocketServer } from "ws";
import { parseRequestUrl } from "./dashboard-server.mjs";
import { WEB_OPERATOR_SESSION_COOKIE, unsealWebOperatorToken } from "./web-operator-session-seal.mjs";

export const RELAY_PATH_PREFIX = "/api/runtime/relay/";

/**
 * Largest message a browser may send through the relay: 4 MiB, the inbound
 * limit of the runtime's aiohttp terminal endpoint (aiohttp's default
 * max_msg_size), so the relay refuses no message the runtime would take.
 * xterm hands over a whole paste as one input message. Clients otherwise send
 * resize events, noVNC key, pointer and clipboard events, and browser-view
 * control messages, all far smaller. ws checks the length in the frame header,
 * so a larger frame closes the connection with 1009 before its payload is
 * read. ws's default is 100 MiB.
 */
export const RELAY_CLIENT_MAX_PAYLOAD_BYTES = 4 * 1024 * 1024;

/**
 * Largest message the relay accepts from the runtime. Terminal output and
 * browser snapshots are small JSON messages, and websockify forwards noVNC
 * traffic in chunks of at most 64 KiB. 4 MiB is also the inbound limit of the
 * runtime's own aiohttp WebSocket endpoints (aiohttp's default max_msg_size).
 */
export const RELAY_UPSTREAM_MAX_PAYLOAD_BYTES = 4 * 1024 * 1024;

/**
 * @typedef {object} RelayDescriptor
 * @property {string} upstreamUrl
 * @property {Record<string, string>} [upstreamHeaders]
 * @property {string} expiresAt
 * @property {string} [tokenHash] sha256 hex of the operator session token
 */

/**
 * @typedef {object} RelayStore
 * @property {Map<string, RelayDescriptor>} descriptors
 */

/**
 * @param {RelayDescriptor} descriptor
 * @returns {boolean}
 */
function isExpired(descriptor) {
  const expiresAt = Date.parse(String(descriptor.expiresAt || ""));
  return !Number.isFinite(expiresAt) || expiresAt <= Date.now();
}

/**
 * The live descriptor for a relay id, or null. An expired one is removed.
 * @param {RelayStore} store
 * @param {string} relayId
 * @returns {RelayDescriptor | null}
 */
export function readRelayDescriptor(store, relayId) {
  const descriptor = store.descriptors.get(relayId) ?? null;
  if (!descriptor) return null;
  if (isExpired(descriptor)) {
    store.descriptors.delete(relayId);
    return null;
  }
  return descriptor;
}

/**
 * The operator session token in the request's session cookie, or null when
 * the cookie is missing or was not sealed under the current key. This is the
 * cookie the browser sends with the handshake. The token is never taken from
 * the URL, where it would reach access logs.
 * @param {import("node:http").IncomingMessage} request
 * @returns {string | null}
 */
function sessionToken(request) {
  const header = request.headers.cookie;
  if (typeof header !== "string") return null;
  for (const pair of header.split(";")) {
    const separator = pair.indexOf("=");
    if (separator === -1 || pair.slice(0, separator).trim() !== WEB_OPERATOR_SESSION_COOKIE) continue;
    try {
      return unsealWebOperatorToken(decodeURIComponent(pair.slice(separator + 1).trim()));
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Whether `token` is the session token whose sha256 the descriptor holds,
 * compared in constant time. A descriptor without a hash admits nobody.
 * @param {RelayDescriptor} descriptor
 * @param {string | null} token
 * @returns {boolean}
 */
function tokenMatches(descriptor, token) {
  if (!descriptor.tokenHash || !token) return false;
  const expected = Buffer.from(String(descriptor.tokenHash), "hex");
  const actual = createHash("sha256").update(token).digest();
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

/**
 * The origin of a dashboard page served at the request's target, by the rule
 * request-origin.ts applies to the dashboard's other routes: the scheme in the
 * first `X-Forwarded-Proto` entry, which a TLS-terminating proxy sends
 * (docs/install/vps.md), or http, the scheme this server listens on; then the
 * Host header. ws and wss stand for http and https: Traefik sends them for a
 * WebSocket.
 * @param {import("node:http").IncomingMessage} request
 * @returns {string | null}
 */
function dashboardOrigin(request) {
  const host = request.headers.host;
  if (typeof host !== "string" || !host) return null;
  const forwarded = request.headers["x-forwarded-proto"];
  const proto = (typeof forwarded === "string" ? forwarded.split(",")[0].trim().toLowerCase() : "") || "http";
  const scheme = proto === "wss" ? "https" : proto === "ws" ? "http" : proto;
  return `${scheme}://${host.toLowerCase()}`;
}

/**
 * Whether the upgrade comes from a dashboard page. A browser sends the page's
 * origin with every WebSocket handshake, and a page cannot change it. The
 * session cookie is SameSite=Strict, so a browser still attaches it for a page
 * on another origin of the same site (another port on the same host, a sibling
 * subdomain): this check refuses that page.
 * @param {import("node:http").IncomingMessage} request
 * @returns {boolean}
 */
function fromDashboardOrigin(request) {
  const origin = request.headers.origin;
  const expected = dashboardOrigin(request);
  return typeof origin === "string" && expected !== null && origin.toLowerCase() === expected;
}

/**
 * Decides an upgrade before any WebSocket work: 403 unless it comes from a
 * dashboard page, 404 for an unknown or expired relay, 401 unless the session
 * cookie holds the token of the operator who attached.
 * @param {RelayStore} store
 * @param {import("node:http").IncomingMessage} request
 * @param {URL} url the request target, as the upgrade router parsed it
 * @returns {{ descriptor: RelayDescriptor } | { status: 401 | 403 | 404 }}
 */
export function authorizeRelayUpgrade(store, request, url) {
  if (!fromDashboardOrigin(request)) return { status: 403 };
  const relayId = url.pathname.slice(RELAY_PATH_PREFIX.length);
  const descriptor = relayId ? readRelayDescriptor(store, relayId) : null;
  if (!descriptor?.upstreamUrl) return { status: 404 };
  if (!tokenMatches(descriptor, sessionToken(request))) return { status: 401 };
  return { descriptor };
}

/**
 * Answers an upgrade with a plain HTTP status and closes the socket. Node's
 * http server removes its own error listener from the socket before it emits
 * "upgrade", so this adds one first: a client that resets the connection while
 * the refusal is written would otherwise raise an uncaught ECONNRESET.
 * @param {import("node:stream").Duplex} socket
 * @param {number} status
 */
function refuseUpgrade(socket, status) {
  socket.on("error", () => socket.destroy());
  if (!socket.writable) {
    socket.destroy();
    return;
  }
  socket.once("finish", () => socket.destroy());
  socket.end(
    `HTTP/1.1 ${status} ${STATUS_CODES[status]}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`,
  );
}

/**
 * @param {WebSocket} socket
 * @param {number} code
 * @param {string} reason
 */
function closeSocket(socket, code, reason) {
  if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
    socket.close(code, reason);
  }
}

/**
 * Bridges an accepted client to the descriptor's upstream.
 * @param {WebSocket} client
 * @param {RelayDescriptor} descriptor
 */
function bridge(client, descriptor) {
  const upstream = new WebSocket(String(descriptor.upstreamUrl), {
    headers:
      descriptor.upstreamHeaders && typeof descriptor.upstreamHeaders === "object"
        ? descriptor.upstreamHeaders
        : undefined,
    maxPayload: RELAY_UPSTREAM_MAX_PAYLOAD_BYTES,
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

/**
 * @param {{ store: RelayStore }} options
 */
export function createRuntimeRelay({ store }) {
  const wss = new WebSocketServer({
    noServer: true,
    maxPayload: RELAY_CLIENT_MAX_PAYLOAD_BYTES,
    perMessageDeflate: false,
  });

  return {
    /**
     * @param {import("node:http").IncomingMessage} request
     * @param {import("node:stream").Duplex} socket
     * @param {Buffer} head
     * @param {URL} url the request target, as the upgrade router parsed it
     */
    handleUpgrade(request, socket, head, url) {
      const decision = authorizeRelayUpgrade(store, request, url);
      if ("status" in decision) {
        refuseUpgrade(socket, decision.status);
        return;
      }
      wss.handleUpgrade(request, socket, head, (client) => bridge(client, decision.descriptor));
    },

    /**
     * @param {number} code
     * @param {string} reason
     */
    closeAll(code, reason) {
      wss.clients.forEach((client) => closeSocket(client, code, reason));
    },
  };
}

/**
 * The dashboard's upgrade handler (server.mjs). Relay paths go to the relay.
 * `/_next/` paths go to `nextUpgrade` when server.mjs passes one: Next.js's
 * dev HMR socket. Every other upgrade gets 404 at once. This app has no
 * rewrites, so Next.js accepts no other upgrade, and it leaves one it does not
 * match open without an answer.
 * @param {{
 *   relay: ReturnType<typeof createRuntimeRelay>,
 *   nextUpgrade?: ((request: import("node:http").IncomingMessage, socket: import("node:stream").Duplex, head: Buffer) => unknown) | null,
 * }} options
 * @returns {(request: import("node:http").IncomingMessage, socket: import("node:stream").Duplex, head: Buffer) => void}
 */
export function createUpgradeRouter({ relay, nextUpgrade = null }) {
  return (request, socket, head) => {
    const url = parseRequestUrl(request);
    if (!url) {
      socket.destroy();
      return;
    }
    if (url.pathname.startsWith(RELAY_PATH_PREFIX)) {
      relay.handleUpgrade(request, socket, head, url);
      return;
    }
    if (nextUpgrade && url.pathname.startsWith("/_next/")) {
      void nextUpgrade(request, socket, head);
      return;
    }
    refuseUpgrade(socket, 404);
  };
}
