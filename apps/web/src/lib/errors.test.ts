import { describe, expect, it } from "vitest";
import {
  ApiError,
  ValidationError,
  toAppError,
  toPublicErrorMessage,
} from "@/lib/errors";

describe("errors", () => {
  it("preserves AppError instances", () => {
    const error = new ApiError("Nope", 404);

    expect(toAppError(error)).toBe(error);
  });

  it("falls back to safe public messages when the error should not expose details", () => {
    const error = new Error("Sensitive upstream detail");

    expect(toPublicErrorMessage(error, "Generic failure")).toBe("Sensitive upstream detail");
    expect(toPublicErrorMessage(new ValidationError("Invalid input"), "Generic failure")).toBe("Invalid input");
  });
});
