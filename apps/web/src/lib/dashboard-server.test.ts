// @vitest-environment node

import { readFile } from "node:fs/promises";
import http from "node:http";
import type { AddressInfo } from "node:net";
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
});
