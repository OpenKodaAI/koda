import { NextResponse } from "next/server";
import type { z } from "zod";
import {
  UpstreamUnavailableError,
  ValidationError,
  toAppError,
  toPublicErrorMessage,
} from "@/lib/errors";

/** Parse a numeric query param with validation and default. */
export function parseIntParam(
  value: string | null,
  defaultValue: number,
  min: number = 1,
  max: number = 1000
): number {
  if (value === null) return defaultValue;
  const parsed = parseInt(value, 10);
  if (isNaN(parsed) || parsed < min || parsed > max) return defaultValue;
  return parsed;
}

export function parseSchemaOrThrow<T>(
  schema: z.ZodType<T>,
  input: unknown,
  message = "Invalid request parameters.",
) {
  const result = schema.safeParse(input);
  if (!result.success) {
    const fieldErrors: Record<string, string[]> = {};
    for (const issue of result.error.issues) {
      const path = issue.path.join(".") || "_root";
      if (!fieldErrors[path]) fieldErrors[path] = [];
      fieldErrors[path].push(issue.message);
    }
    throw new ValidationError(message, {
      cause: result.error,
      fieldErrors,
    });
  }

  return result.data;
}

export function jsonErrorResponse(
  error: unknown,
  fallbackMessage = "Unable to complete the request.",
) {
  const appError = toAppError(error, fallbackMessage);
  const publicMessage =
    appError.code === "VALIDATION_ERROR" ||
    appError.code === "API_ERROR" ||
    appError.code === "NOT_FOUND" ||
    appError.code === "UNAUTHORIZED" ||
    appError.code === "FORBIDDEN" ||
    appError.code === "UPSTREAM_UNAVAILABLE"
      ? toPublicErrorMessage(appError, fallbackMessage)
      : fallbackMessage;

  const body: Record<string, unknown> = { error: publicMessage };

  if (appError instanceof ValidationError && appError.fieldErrors) {
    body.fieldErrors = appError.fieldErrors;
  }

  return NextResponse.json(body, {
    status: appError.status,
    headers: {
      "Cache-Control": "no-store",
    },
  });
}

/**
 * Hard ceiling for any direct upstream fetch from a route handler. Mirrors
 * the timeout in `controlPlaneFetch` so routes that need raw `Response`
 * (auth/login, register-owner, recovery flows…) get the same fast-fail
 * semantics: a missing or hung backend turns into `UpstreamUnavailableError`
 * (503) instead of leaking `TypeError: fetch failed` to the browser.
 */
const UPSTREAM_FETCH_TIMEOUT_MS = 6_000;

function combineSignals(
  caller: AbortSignal | null | undefined,
  timeout: AbortSignal,
): AbortSignal {
  if (!caller) return timeout;
  const factory = (AbortSignal as unknown as { any?: (signals: AbortSignal[]) => AbortSignal })
    .any;
  return typeof factory === "function" ? factory([caller, timeout]) : caller;
}

export async function upstreamFetch(
  url: string | URL,
  init: RequestInit = {},
  options: { timeoutMs?: number; label?: string } = {},
): Promise<Response> {
  const timeoutMs = options.timeoutMs ?? UPSTREAM_FETCH_TIMEOUT_MS;
  const label = options.label ?? "Backend";
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const signal = combineSignals(init.signal, timeoutSignal);

  try {
    return await fetch(url, { ...init, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new UpstreamUnavailableError(
        `${label} did not respond within ${timeoutMs}ms`,
        { cause: error },
      );
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      // Caller-initiated abort — re-throw so the route can handle it.
      throw error;
    }
    throw new UpstreamUnavailableError(
      `${label} is unavailable`,
      { cause: error },
    );
  }
}
