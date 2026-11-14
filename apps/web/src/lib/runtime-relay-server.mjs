/**
 * The runtime relay: a WebSocket at `/api/runtime/relay/<id>` that the
 * dashboard bridges to a worker's terminal, browser snapshot or noVNC socket.
 * server.mjs routes relay-path upgrades here. The relay descriptor (written by
 * `runtime-relay.ts` when an operator attaches) and the session token are
 * checked before the WebSocket handshake, so a request that is not
 * authorised gets a plain HTTP refusal: no WebSocket, no frame parsing and no
 * upstream connection.
 */

import { createHash, timingSafeEqual } from "node:crypto";
import { STATUS_CODES } from "node:http";
import { WebSocket, WebSocketServer } from "ws";

export const RELAY_PATH_PREFIX = "/api/runtime/relay/";

/**
 * Largest message a browser may send through the relay. Clients send
 * terminal input and resize events, noVNC key, pointer and clipboard events,
 * and browser-view control messages, all far below this. ws checks the length
 * in the frame header, so a larger frame closes the connection with 1009
 * before its payload is read. ws's default is 100 MiB.
 */
export const RELAY_CLIENT_MAX_PAYLOAD_BYTES = 1024 * 1024;

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
 * Decides an upgrade before any WebSocket work: 404 for an unknown or expired
 * relay, 401 for a missing or wrong token.
 * @param {RelayStore} store
 * @param {URL} url the request target, as server.mjs parsed it
 * @returns {{ descriptor: RelayDescriptor } | { status: 401 | 404 }}
 */
export function authorizeRelayUpgrade(store, url) {
  const relayId = url.pathname.slice(RELAY_PATH_PREFIX.length);
  const descriptor = relayId ? readRelayDescriptor(store, relayId) : null;
  if (!descriptor?.upstreamUrl) return { status: 404 };
  if (!tokenMatches(descriptor, url.searchParams.get("token"))) return { status: 401 };
  return { descriptor };
}

/**
 * Answers an upgrade with a plain HTTP status and closes the socket.
 * @param {import("node:stream").Duplex} socket
 * @param {number} status
 */
function refuseUpgrade(socket, status) {
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
     * @param {URL} url the request target, as server.mjs parsed it
     */
    handleUpgrade(request, socket, head, url) {
      const decision = authorizeRelayUpgrade(store, url);
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
