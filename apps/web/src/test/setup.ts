import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

if (typeof window !== "undefined") {
  const storageState = new Map<string, string>();
  const localStorageValue: Storage = {
    get length() {
      return storageState.size;
    },
    clear: vi.fn(() => {
      storageState.clear();
    }),
    getItem: vi.fn((key: string) => storageState.get(key) ?? null),
    key: vi.fn((index: number) => Array.from(storageState.keys())[index] ?? null),
    removeItem: vi.fn((key: string) => {
      storageState.delete(key);
    }),
    setItem: vi.fn((key: string, value: string) => {
      storageState.set(key, String(value));
    }),
  };

  Object.defineProperty(window, "localStorage", {
    value: localStorageValue,
    writable: true,
    configurable: true,
  });

  Object.defineProperty(window, "scrollTo", {
    value: vi.fn(),
    writable: true,
  });
}

if (typeof HTMLElement !== "undefined") {
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    value: vi.fn(),
    writable: true,
  });

  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    value: vi.fn(),
    writable: true,
  });
}
