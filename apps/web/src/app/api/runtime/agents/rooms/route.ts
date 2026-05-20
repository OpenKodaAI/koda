import { NextRequest, NextResponse } from "next/server";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { languageSchema } from "@/lib/contracts/common";
import { LOCALE_COOKIE_KEY } from "@/lib/i18n";
import { getRuntimeOverview } from "@/lib/runtime-api";
import {
  buildRuntimeRoomRows,
  matchesRuntimeRoomFilter,
  type RuntimeRoomFilter,
  type RuntimeRoomRow,
} from "@/lib/runtime-overview-model";
import type { PaginatedListResponse } from "@/lib/pagination";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const AGENT_ID_PATTERN = /^[A-Za-z0-9:_-]+$/;
const MAX_AGENTS_PER_REQUEST = 50;
const MAX_LIMIT = 100;

function parseBoundedInt(value: string | null, fallback: number, min: number, max: number) {
  const parsed = value ? Number.parseInt(value, 10) : fallback;
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
    return fallback;
  }
  return parsed;
}

function pagePayload<T>(items: T[], limit: number, offset: number): PaginatedListResponse<T> {
  const pageItems = items.slice(offset, offset + limit);
  const nextOffset = offset + pageItems.length;
  const hasMore = nextOffset < items.length;
  return {
    items: pageItems,
    page: {
      limit,
      offset,
      returned: pageItems.length,
      next_offset: hasMore ? nextOffset : null,
      has_more: hasMore,
      total: null,
    },
  };
}

function matchesSearch(row: RuntimeRoomRow, search: string) {
  if (!search) return true;
  const haystack = [
    row.agentId,
    row.queryText,
    row.queue?.query_text,
    row.environment?.branch_name,
    row.environment?.workspace_path,
    row.phase,
    row.status,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(search);
}

export async function GET(request: NextRequest) {
  let language: string;

  try {
    language = parseSchemaOrThrow(
      languageSchema,
      request.nextUrl.searchParams.get("lang") ?? request.cookies.get(LOCALE_COOKIE_KEY)?.value,
    );
  } catch (error) {
    return jsonErrorResponse(error, "Invalid runtime rooms request.");
  }

  const agentIds = [
    ...new Set(
      (request.nextUrl.searchParams.get("agents") ?? "")
        .split(",")
        .map((id) => id.trim())
        .filter((id) => id.length > 0 && id.length <= 120 && AGENT_ID_PATTERN.test(id)),
    ),
  ].slice(0, MAX_AGENTS_PER_REQUEST);
  const filter = (request.nextUrl.searchParams.get("status") || "all") as RuntimeRoomFilter;
  const search = (request.nextUrl.searchParams.get("search") || "").trim().toLowerCase();
  const limit = parseBoundedInt(request.nextUrl.searchParams.get("limit"), 25, 1, MAX_LIMIT);
  const offset = parseBoundedInt(request.nextUrl.searchParams.get("offset"), 0, 0, 100_000);

  if (agentIds.length === 0) {
    return NextResponse.json(pagePayload([], limit, offset));
  }

  const results = await Promise.allSettled(
    agentIds.map((agentId) => getRuntimeOverview(agentId, language)),
  );
  const overviews = results
    .filter((result): result is PromiseFulfilledResult<Awaited<ReturnType<typeof getRuntimeOverview>>> =>
      result.status === "fulfilled",
    )
    .map((result) => result.value);

  const rows = buildRuntimeRoomRows(overviews).filter(
    (row) => matchesRuntimeRoomFilter(row, filter) && matchesSearch(row, search),
  );

  return NextResponse.json(pagePayload(rows, limit, offset));
}
