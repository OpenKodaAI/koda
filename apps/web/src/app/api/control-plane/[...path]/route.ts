import { NextRequest } from "next/server";
import { revalidatePath, revalidateTag } from "next/cache";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { pathSegmentsSchema } from "@/lib/contracts/common";
import { controlPlaneFetch, sanitizeControlPlanePayload } from "@/lib/control-plane";
import { getControlPlaneMutationInvalidation } from "@/lib/control-plane-cache";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function proxy(request: NextRequest, { params }: RouteContext) {
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

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();

  let response: Response;
  try {
    response = await controlPlaneFetch(
      upstreamUrl.pathname + upstreamUrl.search,
      {
        method: request.method,
        headers: {
          "Content-Type":
            request.headers.get("content-type") || "application/json",
        },
        body,
      },
      { tier: "live" },
    );
  } catch (error) {
    return jsonErrorResponse(error, "Control plane upstream is unavailable");
  }

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  headers.set("Cache-Control", "no-store");
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
    return new Response(
      JSON.stringify(sanitizeControlPlanePayload(pathname, payload)),
      {
        status: response.status,
        headers,
      },
    );
  }

  return new Response(response.body, {
    status: response.status,
    headers,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
