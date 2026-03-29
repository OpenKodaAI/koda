import { NextResponse } from "next/server";
import type { z } from "zod";
import { ValidationError, toAppError, toPublicErrorMessage } from "@/lib/errors";

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
    throw new ValidationError(message, {
      cause: result.error,
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

  return NextResponse.json(
    {
      error: publicMessage,
    },
    {
      status: appError.status,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
