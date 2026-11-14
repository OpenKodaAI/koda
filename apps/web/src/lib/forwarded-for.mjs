/**
 * Decides which client a dashboard request belongs to. The dashboard server
 * (`dashboard-server.mjs`, started by server.mjs) runs this on every request
 * because it is the only code that sees the TCP socket.
 *
 * Next.js writes the socket address into `x-forwarded-for` only when the header
 * is missing. A client that reaches this server directly could therefore send
 * its own value and pick its rate-limit bucket, here and in the control plane.
 * `rewriteForwardedFor` replaces the header with one address. Normally that is
 * the TCP peer. When the peer is a trusted proxy, it is the first untrusted
 * hop, read from the right; entries further left are client-supplied.
 *
 * Loopback is always trusted. `WEB_TRUSTED_PROXIES` adds IPs, CIDRs and the
 * keyword `gateway`: this host's IPv4 default gateway, which inside a Docker
 * container is the address Docker's port proxy connects from. Hostnames are
 * not accepted; a proxy container is trusted by a fixed address.
 */

import { readFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";

const IPV4_MAPPED = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/;
const LOOPBACK = ["127.0.0.1", "::1"];
const RTF_GATEWAY = 0x2;

/**
 * Canonical text of an IP address (IPv4-mapped IPv6 becomes IPv4), or null.
 * @param {unknown} value
 * @returns {string | null}
 */
export function normalizeAddress(value) {
  const text = String(value ?? "").trim().toLowerCase();
  const address = IPV4_MAPPED.exec(text)?.[1] ?? text;
  return net.isIP(address) ? address : null;
}

/**
 * IPv4 default gateway from the text of `/proc/net/route`, or null.
 * The kernel prints addresses as host-order hex words.
 * @param {string} table
 * @param {"BE" | "LE"} [endianness]
 * @returns {string | null}
 */
export function defaultGatewayFromRouteTable(table, endianness = os.endianness()) {
  for (const line of String(table).split("\n").slice(1)) {
    const [, destination, gateway, flags] = line.trim().split(/\s+/);
    if (destination !== "00000000" || !gateway || !(Number.parseInt(flags, 16) & RTF_GATEWAY)) continue;
    const word = Number.parseInt(gateway, 16);
    if (!Number.isInteger(word) || word === 0) continue;
    const bytes = Buffer.alloc(4);
    bytes.writeUInt32BE(word >>> 0);
    if (endianness === "LE") bytes.reverse();
    return [...bytes].join(".");
  }
  return null;
}

/** @returns {string | null} */
export function readDefaultGateway(routeTablePath = "/proc/net/route") {
  try {
    return defaultGatewayFromRouteTable(readFileSync(routeTablePath, "utf8"));
  } catch {
    return null;
  }
}

/**
 * Parses `WEB_TRUSTED_PROXIES`. Entries that are not an IP, a CIDR or
 * `gateway` (or `gateway` when there is no default route) land in `ignored`.
 * @param {string | undefined} spec
 * @param {{ gateway?: () => string | null }} [options]
 * @returns {{ isTrusted: (address: string) => boolean, trusted: string[], ignored: string[] }}
 */
export function parseTrustedProxies(spec, { gateway = readDefaultGateway } = {}) {
  const list = new net.BlockList();
  const trusted = [];
  const ignored = [];
  const family = (/** @type {string} */ address) => (net.isIP(address) === 6 ? "ipv6" : "ipv4");

  for (const address of LOOPBACK) {
    list.addAddress(address, family(address));
    trusted.push(address);
  }
  for (const raw of String(spec ?? "").split(",")) {
    const entry = raw.trim();
    if (!entry) continue;
    if (entry.toLowerCase() === "gateway") {
      const address = normalizeAddress(gateway());
      if (address) {
        list.addAddress(address, family(address));
        trusted.push(`${address} (gateway)`);
      } else {
        ignored.push(entry);
      }
      continue;
    }
    const [base, prefix, ...rest] = entry.split("/");
    const address = normalizeAddress(base);
    const maxPrefix = address && net.isIP(address) === 6 ? 128 : 32;
    if (!address || rest.length > 0) {
      ignored.push(entry);
    } else if (prefix === undefined) {
      list.addAddress(address, family(address));
      trusted.push(address);
    } else if (/^\d{1,3}$/.test(prefix) && Number(prefix) <= maxPrefix) {
      list.addSubnet(address, Number(prefix), family(address));
      trusted.push(`${address}/${prefix}`);
    } else {
      ignored.push(entry);
    }
  }
  return {
    isTrusted: (address) => list.check(address, family(address)),
    trusted,
    ignored,
  };
}

/**
 * The address a request is attributed to, or null when the peer is unknown.
 * @param {string | undefined} peer TCP peer address
 * @param {string | string[] | undefined} forwardedFor incoming `x-forwarded-for`
 * @param {(address: string) => boolean} isTrusted
 * @returns {string | null}
 */
export function resolveClientAddress(peer, forwardedFor, isTrusted) {
  const peerAddress = normalizeAddress(peer);
  if (!peerAddress) return null;
  if (!isTrusted(peerAddress)) return peerAddress;
  const hops = [forwardedFor ?? ""]
    .flat()
    .join(",")
    .split(",")
    .map((hop) => hop.trim())
    .filter(Boolean);
  let client = peerAddress;
  for (const hop of hops.reverse()) {
    const address = normalizeAddress(hop);
    // Unparseable hop: stop at the last address a trusted hop vouched for.
    if (!address) break;
    client = address;
    if (!isTrusted(address)) break;
  }
  return client;
}

/**
 * Replaces `x-forwarded-for` on an incoming Node request with the resolved
 * client address, so everything downstream (Next.js, the dashboard's own rate
 * limiter, the control plane) sees a value the client did not choose.
 * @param {import("node:http").IncomingMessage} request
 * @param {(address: string) => boolean} isTrusted
 */
export function rewriteForwardedFor(request, isTrusted) {
  const client = resolveClientAddress(request.socket?.remoteAddress, request.headers["x-forwarded-for"], isTrusted);
  if (client) {
    request.headers["x-forwarded-for"] = client;
  } else {
    delete request.headers["x-forwarded-for"];
  }
}
