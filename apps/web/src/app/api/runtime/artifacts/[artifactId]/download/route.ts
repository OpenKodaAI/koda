import { NextResponse } from "next/server";
import { runtimeFetch, RuntimeRequestError } from "@/lib/runtime-api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const FORWARDED_HEADERS = [
  "content-type",
  "content-length",
  "content-disposition",
  "accept-ranges",
  "content-range",
  "etag",
  "cache-control",
  "last-modified",
];

const HTML_CONTENT_TYPES = ["text/html", "application/xhtml+xml"];

function isHtmlContentType(value: string | null): boolean {
  if (!value) return false;
  const lower = value.toLowerCase();
  return HTML_CONTENT_TYPES.some((html) => lower.startsWith(html));
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ artifactId: string }> },
) {
  const { artifactId } = await params;
  const url = new URL(request.url);
  const agentId = url.searchParams.get("agent");
  if (!artifactId) {
    return NextResponse.json({ error: "Missing artifact id" }, { status: 400 });
  }
  if (!agentId) {
    return NextResponse.json({ error: "Missing agent id" }, { status: 400 });
  }

  const headers = new Headers();
  const range = request.headers.get("range");
  if (range) headers.set("Range", range);
  const ifNoneMatch = request.headers.get("if-none-match");
  if (ifNoneMatch) headers.set("If-None-Match", ifNoneMatch);

  try {
    const upstream = await runtimeFetch(
      agentId,
      `/api/runtime/artifacts/${encodeURIComponent(artifactId)}/download`,
      {
        method: "GET",
        headers,
        timeoutMs: 60_000,
      },
    );

    if (!upstream.ok || !upstream.body) {
      const text = await upstream.text().catch(() => "");
      return NextResponse.json(
        { error: text || `Unable to fetch artifact (${upstream.status})` },
        { status: upstream.status },
      );
    }

    const responseHeaders = new Headers();
    for (const name of FORWARDED_HEADERS) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }

    // Defense in depth: never let HTML render inline.
    const contentType = upstream.headers.get("content-type");
    if (isHtmlContentType(contentType)) {
      responseHeaders.set(
        "content-disposition",
        responseHeaders.get("content-disposition")?.replace(/^inline/i, "attachment") ??
          "attachment",
      );
    }
    responseHeaders.set("X-Content-Type-Options", "nosniff");

    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const status = error instanceof RuntimeRequestError ? error.status : 500;
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to proxy artifact download",
      },
      { status },
    );
  }
}
