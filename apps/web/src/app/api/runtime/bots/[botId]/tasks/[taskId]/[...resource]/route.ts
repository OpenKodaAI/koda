import { NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import {
  botIdSchema,
  pathSegmentsSchema,
  taskIdParamSchema,
} from "@/lib/contracts/common";
import {
  requireRuntimeBotConfig,
  runtimeFetch,
  runtimeFetchJson,
  RuntimeRequestError,
} from "@/lib/runtime-api";
import {
  createRuntimeRelayDescriptor,
  getRuntimeRelayPath,
  toAbsoluteUpstreamWsUrl,
} from "@/lib/runtime-relay";
import type { RuntimeMutationResult } from "@/lib/runtime-types";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import { getWebOperatorTokenFromCookie } from "@/lib/web-operator-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ATTACH_TERMINAL_TIMEOUT_MS = Number.parseInt(
  process.env.RUNTIME_ATTACH_TERMINAL_TIMEOUT_MS ||
    process.env.RUNTIME_ATTACH_TIMEOUT_MS ||
    "45000",
  10,
);
const ATTACH_BROWSER_TIMEOUT_MS = Number.parseInt(
  process.env.RUNTIME_ATTACH_BROWSER_TIMEOUT_MS ||
    process.env.RUNTIME_ATTACH_TIMEOUT_MS ||
    "30000",
  10,
);

function unauthorizedResponse() {
  return NextResponse.json(
    { error: "Operator session is required." },
    {
      status: 401,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

function forbiddenMutationResponse() {
  return NextResponse.json(
    { error: "Cross-site dashboard mutations are blocked." },
    {
      status: 403,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

function sanitizeAttachPayload(payload: Record<string, unknown>) {
  const sanitized = { ...payload };
  const attach = payload.attach as Record<string, unknown> | undefined;
  if (attach) {
    const nextAttach = { ...attach };
    delete nextAttach.token;
    sanitized.attach = nextAttach;
  }
  delete sanitized.ws_url;
  delete sanitized.novnc_url;
  return sanitized;
}

function joinResourcePath(segments: string[]) {
  return segments.join("/");
}

function cloneSearchParams(request: Request) {
  const url = new URL(request.url);
  return new URLSearchParams(url.searchParams);
}

async function parseRequestParams(
  params: Promise<{ botId: string; taskId: string; resource: string[] }>,
) {
  const parsed = await params;
  return {
    botId: parseSchemaOrThrow(botIdSchema, parsed.botId, "Invalid bot id."),
    taskId: parseSchemaOrThrow(taskIdParamSchema, parsed.taskId, "Invalid task id."),
    resource: parseSchemaOrThrow(
      pathSegmentsSchema,
      parsed.resource ?? [],
      "Invalid runtime resource path.",
    ),
  };
}

async function proxyJson(
  botId: string,
  pathname: string,
  init: RequestInit = {},
  searchParams?: URLSearchParams,
  capability: "read" | "mutate" | "attach" = "read",
) {
  const response = await runtimeFetch(botId, pathname, init, searchParams, {
    capability,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json().catch(() => ({ error: "Invalid JSON response" }))
    : { error: await response.text().catch(() => "Runtime request failed") };
  return NextResponse.json(body, { status: response.status });
}

async function proxyBinary(
  botId: string,
  pathname: string,
  init: RequestInit = {},
  searchParams?: URLSearchParams,
  capability: "read" | "mutate" | "attach" = "read",
) {
  const response = await runtimeFetch(botId, pathname, init, searchParams, {
    capability,
  });
  const body = await response.arrayBuffer();
  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  const cacheControl = response.headers.get("cache-control");

  if (contentType) headers.set("content-type", contentType);
  if (cacheControl) headers.set("cache-control", cacheControl);

  return new NextResponse(body, {
    status: response.status,
    headers,
  });
}

async function buildTerminalAttachResponse(
  botId: string,
  taskId: number,
  payload: Record<string, unknown>,
  sessionToken?: string,
) {
  const bot = await requireRuntimeBotConfig(botId);
  const attach = payload.attach as Record<string, unknown> | undefined;
  const terminal = payload.terminal as Record<string, unknown> | undefined;
  const upstreamWs = typeof payload.ws_url === "string" ? payload.ws_url : null;
  const attachToken = typeof attach?.token === "string" ? attach.token : null;

  if (!attach || !upstreamWs) {
    return NextResponse.json(sanitizeAttachPayload(payload), { status: 200 });
  }

  const relay = await createRuntimeRelayDescriptor({
    kind: "terminal",
    botId,
    taskId,
    terminalId: terminal?.id ? Number(terminal.id) : null,
    upstreamUrl: toAbsoluteUpstreamWsUrl(bot.runtimeBaseUrl, upstreamWs),
    upstreamHeaders: attachToken
      ? {
          "X-Koda-Attach-Token": attachToken,
        }
      : undefined,
    expiresAt: String(
      attach.expires_at || new Date(Date.now() + 5 * 60_000).toISOString(),
    ),
  }, sessionToken);

  return NextResponse.json({
    ...sanitizeAttachPayload(payload),
    relay_path: getRuntimeRelayPath(relay.id),
  });
}

async function buildBrowserAttachResponse(
  botId: string,
  taskId: number,
  payload: Record<string, unknown>,
  sessionToken?: string,
) {
  const bot = await requireRuntimeBotConfig(botId);
  const attach = payload.attach as Record<string, unknown> | undefined;
  const upstreamSnapshotWs =
    typeof payload.ws_url === "string" ? payload.ws_url : null;
  const upstreamNovncWs =
    typeof payload.novnc_url === "string" ? payload.novnc_url : null;
  const attachToken = typeof attach?.token === "string" ? attach.token : null;
  const expiresAt = String(
    attach?.expires_at || new Date(Date.now() + 5 * 60_000).toISOString(),
  );

  const relaySnapshot = upstreamSnapshotWs
    ? await createRuntimeRelayDescriptor({
        kind: "browser",
        botId,
        taskId,
        upstreamUrl: toAbsoluteUpstreamWsUrl(
          bot.runtimeBaseUrl,
          upstreamSnapshotWs,
        ),
        upstreamHeaders: attachToken
          ? {
              "X-Koda-Attach-Token": attachToken,
            }
          : undefined,
        expiresAt,
      }, sessionToken)
    : null;

  const relayNovnc = upstreamNovncWs
    ? await createRuntimeRelayDescriptor({
        kind: "novnc",
        botId,
        taskId,
        upstreamUrl: toAbsoluteUpstreamWsUrl(
          bot.runtimeBaseUrl,
          upstreamNovncWs,
        ),
        expiresAt,
      }, sessionToken)
    : null;

  return NextResponse.json({
    ...sanitizeAttachPayload(payload),
    relay_snapshot_path: relaySnapshot
      ? getRuntimeRelayPath(relaySnapshot.id)
      : null,
    relay_novnc_path: relayNovnc ? getRuntimeRelayPath(relayNovnc.id) : null,
  });
}

export async function GET(
  request: Request,
  {
    params,
  }: {
    params: Promise<{ botId: string; taskId: string; resource: string[] }>;
  },
) {
  const operatorToken = await getWebOperatorTokenFromCookie();
  if (!operatorToken) {
    return unauthorizedResponse();
  }

  let botId: string;
  let numericTaskId: number;
  let resource: string[];

  try {
    const parsed = await parseRequestParams(params);
    botId = parsed.botId;
    numericTaskId = parsed.taskId;
    resource = parsed.resource;
  } catch (error) {
    return jsonErrorResponse(error, "Invalid runtime request.");
  }

  try {
    const resourcePath = joinResourcePath(resource);
    if (resourcePath === "browser/screenshot") {
      return await proxyBinary(
        botId,
        `/api/runtime/tasks/${numericTaskId}/browser/screenshot`,
        { method: "GET" },
        cloneSearchParams(request),
        "read",
      );
    }

    return await proxyJson(
      botId,
      `/api/runtime/tasks/${numericTaskId}/${resourcePath}`,
      { method: "GET" },
      cloneSearchParams(request),
      "read",
    );
  } catch (error) {
    if (error instanceof RuntimeRequestError) {
      return NextResponse.json(
        {
          error: error.message,
        },
        { status: error.status },
      );
    }

    return jsonErrorResponse(error, "Unable to proxy runtime request");
  }
}

export async function POST(
  request: Request,
  {
    params,
  }: {
    params: Promise<{ botId: string; taskId: string; resource: string[] }>;
  },
) {
  const operatorToken = await getWebOperatorTokenFromCookie();
  if (!operatorToken) {
    return unauthorizedResponse();
  }
  if (!isTrustedDashboardRequest(request)) {
    return forbiddenMutationResponse();
  }

  let botId: string;
  let numericTaskId: number;
  let resource: string[];

  try {
    const parsed = await parseRequestParams(params);
    botId = parsed.botId;
    numericTaskId = parsed.taskId;
    resource = parsed.resource;
  } catch (error) {
    return jsonErrorResponse(error, "Invalid runtime request.");
  }

  const resourcePath = joinResourcePath(resource);
  const searchParams = cloneSearchParams(request);

  try {
    if (resourcePath === "attach/terminal") {
      const response = await runtimeFetchJson<Record<string, unknown>>(
        botId,
        `/api/runtime/tasks/${numericTaskId}/attach/terminal`,
        { method: "POST", timeoutMs: ATTACH_TERMINAL_TIMEOUT_MS },
        searchParams,
        { capability: "attach" },
      );

      if (!response.ok || !response.data) {
        return NextResponse.json(
          { error: response.error || "Unable to attach terminal" },
          { status: response.status },
        );
      }

      return buildTerminalAttachResponse(botId, numericTaskId, response.data, operatorToken);
    }

    if (resourcePath === "attach/browser") {
      const response = await runtimeFetchJson<Record<string, unknown>>(
        botId,
        `/api/runtime/tasks/${numericTaskId}/attach/browser`,
        { method: "POST", timeoutMs: ATTACH_BROWSER_TIMEOUT_MS },
        searchParams,
        { capability: "attach" },
      );

      if (!response.ok || !response.data) {
        return NextResponse.json(
          { error: response.error || "Unable to attach browser" },
          { status: response.status },
        );
      }

      return buildBrowserAttachResponse(botId, numericTaskId, response.data, operatorToken);
    }

    const contentType = request.headers.get("content-type");
    const forwardBody = contentType?.includes("application/json")
      ? await request.text()
      : null;

    const response = await runtimeFetchJson<RuntimeMutationResult>(
      botId,
      `/api/runtime/tasks/${numericTaskId}/${resourcePath}`,
      {
        method: "POST",
        ...(forwardBody
          ? {
              body: forwardBody,
              headers: { "Content-Type": "application/json" },
            }
          : {}),
      },
      searchParams,
      { capability: "mutate" },
    );

    return NextResponse.json(
      response.data ?? { error: response.error || "Runtime mutation failed" },
      { status: response.status },
    );
  } catch (error) {
    if (error instanceof RuntimeRequestError) {
      return NextResponse.json(
        {
          error: error.message,
        },
        { status: error.status },
      );
    }

    return jsonErrorResponse(error, "Unable to proxy runtime mutation");
  }
}
