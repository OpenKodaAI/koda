import { z } from "zod";
import {
  DEFAULT_LANGUAGE,
  normalizeLanguage,
  SUPPORTED_LANGUAGES,
  type AppLanguage,
} from "@/lib/i18n";

const IDENTIFIER_PATTERN = /^[A-Za-z0-9:_-]+$/;

export const botIdSchema = z
  .string()
  .trim()
  .min(1)
  .max(120)
  .regex(IDENTIFIER_PATTERN, "Invalid bot id.");

export const sessionIdSchema = z.string().trim().min(1).max(240);

export const pathSegmentSchema = z
  .string()
  .trim()
  .min(1)
  .max(180)
  .regex(/^[A-Za-z0-9._:-]+$/, "Invalid path segment.");

export const pathSegmentsSchema = z.array(pathSegmentSchema).default([]);

export const taskIdParamSchema = z.coerce
  .number()
  .int()
  .positive();

export const searchTextSchema = z.string().trim().max(240).default("");

export const languageSchema = z
  .string()
  .trim()
  .optional()
  .transform((value): AppLanguage => normalizeLanguage(value ?? DEFAULT_LANGUAGE));

export const optionalLanguageFilterSchema = z.string().trim().max(24).default("");

export const supportedLanguageSchema = z.enum(SUPPORTED_LANGUAGES);

export const retryEligibleFilterSchema = z.enum(["", "eligible", "ineligible"]).default("");
export const costsPeriodSchema = z.enum(["7d", "30d", "90d"]).default("30d");

function toArray(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value;
  }

  return value ? [value] : [];
}

export function parseBotIdList(value: string | string[] | undefined) {
  return z.array(botIdSchema).catch([]).parse(toArray(value));
}
