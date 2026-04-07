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

/**
 * Extract field-level validation errors from a 400 response.
 * NOTE: This consumes the response body. If the body was already read
 * (e.g. via parseResponseError), pass the parsed payload to avoid a
 * failed re-read. Use the overload that accepts a pre-parsed object
 * when the response has already been consumed.
 */
export function parseValidationErrors(payload: Record<string, unknown>): {
  message: string | null;
  fieldErrors: Record<string, string[]> | null;
};
export function parseValidationErrors(response: Response): Promise<{
  message: string | null;
  fieldErrors: Record<string, string[]> | null;
}>;
export function parseValidationErrors(input: Response | Record<string, unknown>) {
  if (!(input instanceof Response)) {
    return {
      message: "error" in input ? String(input.error) : null,
      fieldErrors:
        "fieldErrors" in input
          ? (input.fieldErrors as Record<string, string[]>)
          : null,
    };
  }

  return _parseValidationErrorsFromResponse(input);
}

async function _parseValidationErrorsFromResponse(response: Response) {
  const payload = await response.json().catch(() => null);
  if (payload && typeof payload === "object") {
    return {
      message: "error" in payload ? String(payload.error) : null,
      fieldErrors:
        "fieldErrors" in payload
          ? (payload.fieldErrors as Record<string, string[]>)
          : null,
    };
  }
  return { message: null, fieldErrors: null };
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
