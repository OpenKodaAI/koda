import { describe, expect, it } from "vitest";
import { setCurrentLanguage } from "@/lib/i18n";
import {
  humanizeRuntimeAttachError,
  normalizeRuntimeRequestError,
} from "@/lib/runtime-errors";

setCurrentLanguage("pt-BR");

describe("runtime-errors", () => {
  it("normalizes timeout errors into a stable runtime message", () => {
    expect(
      normalizeRuntimeRequestError(
        new Error("The operation was aborted due to timeout"),
        45_000
      )
    ).toBe("Runtime request timed out after 45s.");
  });

  it("humanizes token errors for browser fallback mode", () => {
    expect(
      humanizeRuntimeAttachError(
        "browser",
        "runtime UI token is not configured",
        "snapshot"
      )
    ).toMatch(/snapshot e metadados/i);
  });
});
