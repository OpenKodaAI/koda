import { NextRequest, NextResponse } from "next/server";
import { revalidatePath, revalidateTag } from "next/cache";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { ValidationError } from "@/lib/errors";
import { pathSegmentsSchema } from "@/lib/contracts/common";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";
import "@/lib/contracts/agents";
import "@/lib/contracts/auth";
import "@/lib/contracts/workspaces";
import "@/lib/contracts/mcp";
import "@/lib/contracts/system";
import "@/lib/contracts/sessions";
import "@/lib/contracts/memory";
import "@/lib/contracts/evals";
import "@/lib/contracts/channel-gateway";
import "@/lib/contracts/onboarding-readiness";
import { controlPlaneFetch, sanitizeControlPlanePayload } from "@/lib/control-plane";
import { getControlPlaneMutationInvalidation } from "@/lib/control-plane-cache";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import {
  getWebOperatorTokenFromCookie,
  setOwnerExistsHintCookie,
} from "@/lib/web-operator-session";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

const PUBLIC_CONTROL_PLANE_PATHS = new Set([
  "onboarding/status",
  "onboarding/readiness",
  "auth/status",
  "auth/bootstrap/exchange",
  "auth/login",
  "auth/register-owner",
]);

function isPublicControlPlanePath(path: string[]) {
  return PUBLIC_CONTROL_PLANE_PATHS.has(path.join("/"));
}

function unauthorizedResponse() {
  return new Response(
    JSON.stringify({ error: "Operator session is required." }),
    {
      status: 401,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    },
  );
}

function forbiddenMutationResponse() {
  return new Response(
    JSON.stringify({ error: "Cross-site dashboard mutations are blocked." }),
    {
      status: 403,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    },
  );
}

async function handleControlPlaneProxy(request: NextRequest, { params }: RouteContext) {
  let path: string[];

  try {
    const raw = await params;
    path = parseSchemaOrThrow(
      pathSegmentsSchema,
      raw.path ?? [],
      "Invalid control plane path.",
    );
  } catch (error) {
    return jsonErrorResponse(error, "Invalid control plane path.");
  }

  const operatorToken = await getWebOperatorTokenFromCookie();
  const publicPath = isPublicControlPlanePath(path);
  if (!operatorToken && !publicPath) {
    return unauthorizedResponse();
  }
  if (!isTrustedDashboardRequest(request)) {
    return forbiddenMutationResponse();
  }

  if (path[path.length - 1] === "runtime-access") {
    return new Response(
      JSON.stringify({
        error: "runtime access is only available from server-side modules",
      }),
      {
        status: 403,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      },
    );
  }
  const pathname = `/api/control-plane/${path.join("/")}`;
  const upstreamUrl = new URL(pathname, "http://local.invalid");
  upstreamUrl.search = request.nextUrl.search;

  let body: string | ArrayBuffer | undefined;
  const incomingContentType = request.headers.get("content-type") || "";
  const isMultipart = incomingContentType.toLowerCase().startsWith("multipart/");

  if (request.method !== "GET" && request.method !== "HEAD") {
    if (isMultipart) {
      // Multipart bodies are binary (and must keep their boundary). Reading
      // them as text mangles the JPEG/PNG bytes and the upstream then sees a
      // length-mismatched payload, which surfaces as a generic
      // "upstream unavailable" to the operator. Forward the bytes as-is and
      // skip JSON-schema validation since multipart is never JSON.
      body = await request.arrayBuffer();
    } else {
      const rawBody = await request.text();

      const schema = resolveBodySchema(request.method, path);
      if (schema && rawBody) {
        let parsed: unknown;
        try {
          parsed = JSON.parse(rawBody);
        } catch {
          return jsonErrorResponse(
            new ValidationError("Request body is not valid JSON."),
            "Invalid request data.",
          );
        }
        try {
          const validated = parseSchemaOrThrow(schema, parsed, "Invalid request data.");
          body = JSON.stringify(validated);
        } catch (error) {
          return jsonErrorResponse(error, "Invalid request data.");
        }
      } else {
        body = rawBody || undefined;
      }
    }
  }

  // Preserve the exact incoming Content-Type — for multipart that includes the
  // boundary token, which is required for the upstream parser to find part
  // separators.
  const upstreamContentType = isMultipart
    ? incomingContentType
    : incomingContentType || "application/json";

  let response: Response;
  try {
    response = await controlPlaneFetch(
      upstreamUrl.pathname + upstreamUrl.search,
      {
        method: request.method,
        headers: {
          "Content-Type": upstreamContentType,
        },
        body,
      },
      {
        tier: "live",
        // Multipart uploads run image-processing work upstream (Pillow decode +
        // re-encode + disk write); the default 10s budget is tight in dev.
        // Bump it for binary bodies so the operator never sees a spurious
        // "upstream unavailable" while the backend is still processing.
        ...(isMultipart ? { timeoutMs: 30_000 } : {}),
      },
    );
  } catch (error) {
    return jsonErrorResponse(error, "Control plane upstream is unavailable");
  }

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  // Dynamic JSON payloads must never be cached, but binary asset responses
  // (room photos, artifact downloads) carry their own immutable cache hints
  // and should be passed through verbatim — otherwise the operator pays for
  // a fresh fetch on every navigation. Honour the upstream Cache-Control /
  // ETag for non-JSON responses; force no-store for JSON.
  if (contentType?.includes("application/json")) {
    headers.set("Cache-Control", "no-store");
  } else {
    const upstreamCacheControl = response.headers.get("cache-control");
    headers.set("Cache-Control", upstreamCacheControl ?? "no-store");
    const upstreamEtag = response.headers.get("etag");
    if (upstreamEtag) headers.set("ETag", upstreamEtag);
    const upstreamLastModified = response.headers.get("last-modified");
    if (upstreamLastModified) headers.set("Last-Modified", upstreamLastModified);
  }
  headers.set("X-Content-Type-Options", "nosniff");

  if (
    response.ok &&
    ["POST", "PUT", "PATCH", "DELETE"].includes(request.method)
  ) {
    const invalidation = getControlPlaneMutationInvalidation(path);

    for (const tag of invalidation.tags) {
      revalidateTag(tag, "max");
    }

    revalidatePath("/", "layout");

    for (const routePath of invalidation.paths) {
      revalidatePath(routePath);
    }
  }

  if (contentType?.includes("application/json")) {
    const payload = await response.json().catch(() => null);
    const sanitized = sanitizeControlPlanePayload(pathname, payload);
    const finalResponse = new NextResponse(JSON.stringify(sanitized), {
      status: response.status,
      headers,
    });
    // Sync the owner-exists hint cookie whenever we observe it from the
    // control plane. Server Component pages cannot set cookies directly, so
    // we do it here on the next response the client sees.
    if (
      pathname === "/api/control-plane/auth/status" ||
      pathname === "/api/control-plane/onboarding/status"
    ) {
      if (sanitized && typeof sanitized === "object" && "has_owner" in sanitized) {
        setOwnerExistsHintCookie(finalResponse, Boolean((sanitized as { has_owner?: boolean }).has_owner));
      }
    }
    return finalResponse;
  }

  return new Response(response.body, {
    status: response.status,
    headers,
  });
}

export const GET = handleControlPlaneProxy;
export const POST = handleControlPlaneProxy;
export const PUT = handleControlPlaneProxy;
export const PATCH = handleControlPlaneProxy;
export const DELETE = handleControlPlaneProxy;
