// @vitest-environment node

import { readFile } from "node:fs/promises";
import http from "node:http";
import net, { type AddressInfo } from "node:net";
import type { Duplex } from "node:stream";
import { afterEach, describe, expect, it } from "vitest";
import { createDashboardServer } from "./dashboard-server.mjs";
import { parseTrustedProxies } from "./forwarded-for.mjs";

type OutgoingHeaders = Record<string, string | string[]>;

// Stand-ins for Next.js and the relay: each reports the header it was handed.
function echoHandle(request: http.IncomingMessage, response: http.ServerResponse) {
  response.end(String(request.headers["x-forwarded-for"] ?? ""));
}

function echoUpgrade(request: http.IncomingMessage, socket: Duplex) {
  socket.end(
    "HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: echo\r\n" +
      `X-Seen-Forwarded-For: ${request.headers["x-forwarded-for"] ?? ""}\r\n\r\n`,
  );
}

// The test client always connects from loopback, which server.mjs trusts. A
// peer that is not a trusted proxy is modelled by trusting nobody.
const trustNobody = () => false;
const { isTrusted: trustLoopback } = parseTrustedProxies("", { gateway: () => null });

const servers: http.Server[] = [];

async function start(isTrusted: (address: string) => boolean): Promise<number> {
  const server = createDashboardServer({ handle: echoHandle, upgrade: echoUpgrade, isTrusted });
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return (server.address() as AddressInfo).port;
}

function get(port: number, path: string, headers: OutgoingHeaders = {}): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = http.request({ host: "127.0.0.1", port, path, headers, agent: false }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk: string) => (body += chunk));
      response.on("end", () => resolve(body));
    });
    request.on("error", reject);
    request.end();
  });
}

function upgrade(port: number, headers: OutgoingHeaders = {}): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = http.request({
      host: "127.0.0.1",
      port,
      path: "/api/runtime/relay/abc",
      headers: { Connection: "Upgrade", Upgrade: "echo", ...headers },
      agent: false,
    });
    request.on("upgrade", (response, socket) => {
      socket.destroy();
      resolve(String(response.headers["x-seen-forwarded-for"]));
    });
    request.on("response", (response) => reject(new Error(`no upgrade: ${response.statusCode}`)));
    request.on("error", reject);
    request.end();
  });
}

// Writes a request verbatim, for bytes Node's HTTP client refuses to send.
// Resolves with the status code and body once the server closes the socket;
// plain requests use HTTP/1.0 so the body is not chunked.
function raw(port: number, lines: string[]): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const socket = net.connect(port, "127.0.0.1", () => socket.end(`${lines.join("\r\n")}\r\n\r\n`));
    let text = "";
    socket.setEncoding("utf8");
    socket.on("data", (chunk: string) => (text += chunk));
    socket.on("error", reject);
    socket.on("close", () => {
      const [head, ...body] = text.split("\r\n\r\n");
      resolve({ status: Number(head.split(" ")[1]), body: body.join("\r\n\r\n") });
    });
  });
}

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      (server) =>
        new Promise<void>((resolve) => {
          server.closeAllConnections();
          server.close(() => resolve());
        }),
    ),
  );
});

describe("createDashboardServer", () => {
  it("replaces a forged x-forwarded-for from an untrusted peer before the request handler runs", async () => {
    const port = await start(trustNobody);

    await expect(get(port, "/api/control-plane/agents", { "X-Forwarded-For": "6.6.6.6" })).resolves.toBe(
      "127.0.0.1",
    );
    // Duplicate header lines, which Node joins into one list, are replaced too.
    await expect(
      get(port, "/api/control-plane/agents", { "X-Forwarded-For": ["6.6.6.6", "7.7.7.7"] }),
    ).resolves.toBe("127.0.0.1");
  });

  it("keeps only the client a trusted proxy reports", async () => {
    const port = await start(trustLoopback);

    await expect(
      get(port, "/api/control-plane/agents", { "X-Forwarded-For": "1.1.1.1, 8.8.8.8" }),
    ).resolves.toBe("8.8.8.8");
  });

  it("rewrites the header on upgrades before the upgrade handler runs", async () => {
    const untrusted = await start(trustNobody);
    const trusted = await start(trustLoopback);

    await expect(upgrade(untrusted, { "X-Forwarded-For": "6.6.6.6" })).resolves.toBe("127.0.0.1");
    await expect(upgrade(trusted, { "X-Forwarded-For": "1.1.1.1, 8.8.8.8" })).resolves.toBe("8.8.8.8");
  });

  it("is the server server.mjs listens with", async () => {
    const source = await readFile(new URL("../../server.mjs", import.meta.url), "utf8");

    expect(source).toMatch(/\bcreateDashboardServer\(\{/);
    expect(source).not.toMatch(/\bcreateServer\(/);
  });

  it("answers the health check itself", async () => {
    const port = await start(trustNobody);

    expect(JSON.parse(await get(port, "/api/health"))).toMatchObject({ status: "ok" });
  });

  it("keeps serving when the Host header or the request target is not a valid URL", async () => {
    const port = await start(trustNobody);

    // The path is routed without the Host header, so a host that is not a URL host is harmless.
    for (const host of ["Host: a b", "Host:"]) {
      const health = await raw(port, ["GET /api/health HTTP/1.0", host]);
      expect(health.status).toBe(200);
      expect(JSON.parse(health.body)).toMatchObject({ status: "ok" });
      await expect(raw(port, ["GET /login HTTP/1.0", host])).resolves.toEqual({
        status: 200,
        body: "127.0.0.1",
      });
    }
    // A target that does not parse even against a fixed base is refused.
    for (const target of ["//a%zz/", "http://[/x"]) {
      await expect(raw(port, [`GET ${target} HTTP/1.0`, "Host: localhost"])).resolves.toEqual({
        status: 400,
        body: "",
      });
    }
    expect(JSON.parse(await get(port, "/api/health"))).toMatchObject({ status: "ok" });
  });

  it("keeps serving upgrades when the Host header or the request target is not a valid URL", async () => {
    const port = await start(trustNobody);
    const upgradeHeaders = ["Connection: Upgrade", "Upgrade: echo"];

    await expect(
      raw(port, ["GET /api/runtime/relay/abc HTTP/1.1", "Host: a b", ...upgradeHeaders]),
    ).resolves.toMatchObject({ status: 101 });
    // The upgrade handler (server.mjs routes on the path) never sees a target that does not parse.
    await expect(raw(port, ["GET //a%zz/ HTTP/1.1", "Host: localhost", ...upgradeHeaders])).resolves.toEqual({
      status: 400,
      body: "",
    });
    await expect(upgrade(port, { "X-Forwarded-For": "6.6.6.6" })).resolves.toBe("127.0.0.1");
  });

  it("is what server.mjs parses request targets with, never the Host header", async () => {
    const source = await readFile(new URL("../../server.mjs", import.meta.url), "utf8");

    expect(source).not.toMatch(/new URL\(/);
    expect(source).not.toMatch(/headers\.host/);
    expect(source.match(/\bparseRequestUrl\(request\)/g)).toHaveLength(2);
  });
});
