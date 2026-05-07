"use client";

import type { StorageCodec } from "@/lib/contracts/storage";

type StorageLike = Storage & Record<string, string | undefined>;

export function getSafeLocalStorage(): StorageLike | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function safeLocalStorageGet(key: string): string | null {
  const storage = getSafeLocalStorage();
  if (!storage) {
    return null;
  }

  try {
    if (typeof storage.getItem === "function") {
      return storage.getItem(key);
    }

    return typeof storage[key] === "string" ? storage[key] : null;
  } catch {
    return null;
  }
}

export function safeLocalStorageSet(key: string, value: string): void {
  const storage = getSafeLocalStorage();
  if (!storage) {
    return;
  }

  try {
    if (typeof storage.setItem === "function") {
      storage.setItem(key, value);
      return;
    }

    storage[key] = value;
  } catch {
    // Best effort.
  }
}

export function safeLocalStorageRemove(key: string): void {
  const storage = getSafeLocalStorage();
  if (!storage) {
    return;
  }

  try {
    if (typeof storage.removeItem === "function") {
      storage.removeItem(key);
      return;
    }

    delete storage[key];
  } catch {
    // Best effort.
  }
}

export function safeLocalStorageGetValue<T>(codec: StorageCodec<T>) {
  return codec.parse(safeLocalStorageGet(codec.key));
}

export function safeLocalStorageSetValue<T>(codec: StorageCodec<T>, value: T) {
  safeLocalStorageSet(codec.key, codec.serialize(value));
}

export function safeLocalStorageRemoveValue<T>(codec: StorageCodec<T>) {
  safeLocalStorageRemove(codec.key);
}

export function readDocumentCookie(name: string) {
  if (typeof document === "undefined") {
    return null;
  }

  const key = `${encodeURIComponent(name)}=`;
  const item = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(key));

  if (!item) {
    return null;
  }

  return decodeURIComponent(item.slice(key.length));
}
