import { ApiError, UpstreamUnavailableError } from "@/lib/errors";
import { parseResponseError, readJsonResponse } from "@/lib/http-client";

type DashboardParamValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Array<string | number | boolean | null | undefined>;

export type DashboardQueryParams = Record<string, DashboardParamValue>;

type DashboardFetchOptions = {
  signal?: AbortSignal;
  params?: DashboardQueryParams;
  fallbackError: string;
};

function appendParam(searchParams: URLSearchParams, key: string, value: DashboardParamValue) {
  if (Array.isArray(value)) {
    for (const item of value) {
      appendParam(searchParams, key, item);
    }
    return;
  }

  if (value === null || value === undefined || value === "") {
    return;
  }

  searchParams.append(key, String(value));
}

export function buildControlPlaneDashboardPath(
  pathname: string,
  params?: DashboardQueryParams,
) {
  const normalizedPath = pathname.startsWith("/")
    ? pathname
    : `/${pathname}`;
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params ?? {})) {
    appendParam(searchParams, key, value);
  }

  const query = searchParams.toString();
  return `/api/control-plane/dashboard${normalizedPath}${query ? `?${query}` : ""}`;
}

export function buildControlPlaneDashboardUrl(
  pathname: string,
  params?: DashboardQueryParams,
) {
  return buildControlPlaneDashboardPath(pathname, params);
}

export async function fetchControlPlaneDashboardJson<T>(
  pathname: string,
  { signal, params, fallbackError }: DashboardFetchOptions,
) {
  const response = await fetch(buildControlPlaneDashboardUrl(pathname, params), {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new ApiError(
      await parseResponseError(response, fallbackError),
      response.status,
    );
  }

  return readJsonResponse<T>(response);
}

export async function fetchControlPlaneDashboardJsonAllowError<T>(
  pathname: string,
  { signal, params, fallbackError }: DashboardFetchOptions,
) {
  const response = await fetch(buildControlPlaneDashboardUrl(pathname, params), {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      data: null as T | null,
      error: await parseResponseError(response, fallbackError),
    };
  }

  return {
    ok: true,
    status: response.status,
    data: await readJsonResponse<T>(response),
    error: null,
  };
}

type DashboardMutationOptions = DashboardFetchOptions & {
  body?: unknown;
  method?: "POST" | "PUT" | "PATCH" | "DELETE";
};

export async function mutateControlPlaneDashboardJson<T>(
  pathname: string,
  {
    signal,
    params,
    fallbackError,
    body,
    method = "POST",
  }: DashboardMutationOptions,
) {
  const response = await fetch(buildControlPlaneDashboardUrl(pathname, params), {
    method,
    signal,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    throw new ApiError(
      await parseResponseError(response, fallbackError),
      response.status,
    );
  }

  return readJsonResponse<T>(response);
}

export function toDashboardUnavailableError(error: unknown, fallbackError: string) {
  if (error instanceof ApiError) {
    return error;
  }

  return new UpstreamUnavailableError(
    error instanceof Error && error.message.trim()
      ? error.message
      : fallbackError,
    { cause: error },
  );
}
