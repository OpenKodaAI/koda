import { describe, expect, it } from "vitest";
import { z } from "zod";
import { createStorageCodec } from "@/lib/contracts/storage";
import { DEFAULT_LANGUAGE, LOCALE_COOKIE_KEY } from "@/lib/i18n";
import {
  appTourStorageCodec,
  localeStorageCodec,
  sidebarCollapsedStorageCodec,
} from "@/lib/storage-codecs";
import { APP_TOUR_STORAGE_KEY, APP_TOUR_VERSION } from "@/lib/tour";

describe("storage codecs", () => {
  it("keeps the exported onboarding-adjacent codecs on stable keys and defaults", () => {
    expect(localeStorageCodec.key).toBe(LOCALE_COOKIE_KEY);
    expect(localeStorageCodec.fallback).toBe(DEFAULT_LANGUAGE);
    expect(sidebarCollapsedStorageCodec.key).toBe("ui:sidebar-collapsed");
    expect(sidebarCollapsedStorageCodec.fallback).toBe(false);
    expect(appTourStorageCodec.key).toBe(APP_TOUR_STORAGE_KEY);
    expect(appTourStorageCodec.fallback).toMatchObject({
      version: APP_TOUR_VERSION,
      status: "pending",
      currentStepId: null,
    });
  });

  it("round-trips valid persisted values and falls back for invalid ones", () => {
    expect(localeStorageCodec.parse(JSON.stringify("pt-BR"))).toBe("pt-BR");
    expect(localeStorageCodec.parse(JSON.stringify("de-DE"))).toBe("de-DE");
    expect(localeStorageCodec.parse(JSON.stringify("fr-FR"))).toBe("fr-FR");
    expect(localeStorageCodec.parse(JSON.stringify("xx-XX"))).toBe(DEFAULT_LANGUAGE);
    expect(sidebarCollapsedStorageCodec.parse(JSON.stringify(true))).toBe(true);
    expect(sidebarCollapsedStorageCodec.parse("not-json")).toBe(false);
  });

  it("treats versioned payload mismatches as incompatible", () => {
    const versionedTourCodec = createStorageCodec(
      "tour:onboarding",
      z.object({
        version: z.literal(2),
        dismissed: z.boolean(),
      }),
      {
        version: 2,
        dismissed: false,
      },
    );

    expect(
      versionedTourCodec.parse(JSON.stringify({ version: 2, dismissed: true })),
    ).toEqual({
      version: 2,
      dismissed: true,
    });
    expect(
      versionedTourCodec.parse(JSON.stringify({ version: 1, dismissed: true })),
    ).toEqual({
      version: 2,
      dismissed: false,
    });
  });
});
