"use client";

import { ApiError } from "@/lib/errors";

export function isAbortError(error: unknown) {
  return (
    error instanceof DOMException && error.name === "AbortError"
  );
}

export function toErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export async function readJsonResponse<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

export async function parseResponseError(
  response: Response,
  fallback: string,
) {
  const payload = await response.json().catch(() => null);
  if (payload && typeof payload === "object" && "error" in payload) {
    return String(payload.error);
  }
  return fallback;
}

export async function requestJson<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new ApiError(
      await parseResponseError(
        response,
        `Request failed with status ${response.status}`,
      ),
      response.status,
    );
  }

  return readJsonResponse<T>(response);
}

export async function requestJsonAllowError<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<{ ok: boolean; status: number; data: T | null; error: string | null }> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  const data = await response.json().catch(() => null);

  return {
    ok: response.ok,
    status: response.status,
    data: data as T | null,
    error:
      !response.ok && data && typeof data === "object" && "error" in data
        ? String(data.error)
        : null,
  };
}
