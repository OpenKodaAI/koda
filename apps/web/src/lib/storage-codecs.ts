import { z } from "zod";
import { createStorageCodec } from "@/lib/contracts/storage";
import {
  DEFAULT_LANGUAGE,
  LOCALE_COOKIE_KEY,
  SUPPORTED_LANGUAGES,
} from "@/lib/i18n";
import {
  APP_TOUR_STORAGE_KEY,
  APP_TOUR_VERSION,
  TOUR_CHAPTER_IDS,
  TOUR_STEP_IDS,
} from "@/lib/tour";

export const localeStorageCodec = createStorageCodec(
  LOCALE_COOKIE_KEY,
  z.enum(SUPPORTED_LANGUAGES),
  DEFAULT_LANGUAGE,
);

export const sidebarCollapsedStorageCodec = createStorageCodec(
  "ui:sidebar-collapsed",
  z.boolean(),
  false,
);

export const THEME_PREFERENCE_STORAGE_KEY = "ui:theme-preference" as const;

export const themePreferenceStorageCodec = createStorageCodec(
  THEME_PREFERENCE_STORAGE_KEY,
  z.enum(["system", "light", "dark"]),
  "system",
);

export const appTourStorageCodec = createStorageCodec(
  APP_TOUR_STORAGE_KEY,
  z.object({
    version: z.number().int().min(1),
    status: z.enum(["pending", "running", "skipped", "completed"]),
    currentStepId: z.enum(TOUR_STEP_IDS).nullable(),
    completedChapters: z.array(z.enum(TOUR_CHAPTER_IDS)),
    updatedAt: z.number().int().nonnegative(),
    completedAt: z.number().int().nonnegative().nullable(),
    skippedAt: z.number().int().nonnegative().nullable(),
  }),
  {
    version: APP_TOUR_VERSION,
    status: "pending",
    currentStepId: null,
    completedChapters: [],
    updatedAt: 0,
    completedAt: null,
    skippedAt: null,
  },
);
