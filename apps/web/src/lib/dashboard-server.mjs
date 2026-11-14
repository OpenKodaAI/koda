/**
 * The dashboard's HTTP server, started by server.mjs. It is the only code that
 * sees the TCP socket, so it rewrites `x-forwarded-for` on every request and
 * every upgrade before any handler runs (`forwarded-for.mjs`). Next.js, the
 * proxy's rate limiter, the WebSocket relay and the control plane therefore
 * all see an address the client did not choose.
 */

import http from "node:http";
import { rewriteForwardedFor } from "./forwarded-for.mjs";

/**
 * @typedef {object} DashboardServerOptions
 * @property {(request: http.IncomingMessage, response: http.ServerResponse) => unknown} handle
 *   request handler (Next.js)
 * @property {(request: http.IncomingMessage, socket: import("node:stream").Duplex, head: Buffer) => void} upgrade
 *   upgrade handler (the runtime relay, then Next.js)
 * @property {(address: string) => boolean} isTrusted peers whose `x-forwarded-for` is believed
 */

/**
 * The request target as a URL, or null when it does not parse. Only the path
 * and query are read, so the base is fixed instead of taken from the client's
 * `Host` header. A `new URL` that throws inside a listener is uncaught and
 * would stop the process (`Host: a b`, or a target such as `//a%zz/`).
 * @param {http.IncomingMessage} request
 * @returns {URL | null}
 */
export function parseRequestUrl(request) {
  try {
    return new URL(request.url ?? "/", "http://localhost");
  } catch {
    return null;
  }
}

/**
 * @param {DashboardServerOptions} options
 * @returns {http.Server}
 */
export function createDashboardServer({ handle, upgrade, isTrusted }) {
  const server = http.createServer((request, response) => {
    rewriteForwardedFor(request, isTrusted);
    const url = parseRequestUrl(request);
    if (!url) {
      response.writeHead(400, { Connection: "close" });
      response.end();
      return;
    }
    if (url.pathname === "/api/health") {
      response.writeHead(200, {
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        "Content-Type": "application/json",
      });
      response.end(JSON.stringify({ status: "ok", timestamp: new Date().toISOString() }));
      return;
    }

    void handle(request, response);
  });

  server.on("upgrade", (request, socket, head) => {
    rewriteForwardedFor(request, isTrusted);
    if (!parseRequestUrl(request)) {
      socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
      return;
    }
    upgrade(request, socket, head);
  });

  return server;
}
