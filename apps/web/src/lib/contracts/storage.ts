import type { z } from "zod";

export type StorageCodec<T> = {
  key: string;
  fallback: T;
  parse: (raw: string | null | undefined) => T;
  serialize: (value: T) => string;
};

export function createStorageCodec<T>(
  key: string,
  schema: z.ZodType<T>,
  fallback: T,
): StorageCodec<T> {
  return {
    key,
    fallback,
    parse(raw) {
      if (raw == null || raw === "") {
        return fallback;
      }

      try {
        return schema.parse(JSON.parse(raw));
      } catch {
        return fallback;
      }
    },
    serialize(value) {
      return JSON.stringify(schema.parse(value));
    },
  };
}
