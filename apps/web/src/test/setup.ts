import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

if (typeof window !== "undefined") {
  const storageState = new Map<string, string>();
  const localStorageValue =
    (window.localStorage as Partial<Storage> | undefined) ?? {};

  if (typeof localStorageValue.getItem !== "function") {
    Object.defineProperty(localStorageValue, "getItem", {
      value: vi.fn((key: string) => storageState.get(key) ?? null),
      writable: true,
      configurable: true,
    });
  }

  if (typeof localStorageValue.setItem !== "function") {
    Object.defineProperty(localStorageValue, "setItem", {
      value: vi.fn((key: string, value: string) => {
        storageState.set(key, String(value));
      }),
      writable: true,
      configurable: true,
    });
  }

  if (typeof localStorageValue.removeItem !== "function") {
    Object.defineProperty(localStorageValue, "removeItem", {
      value: vi.fn((key: string) => {
        storageState.delete(key);
      }),
      writable: true,
      configurable: true,
    });
  }

  if (typeof localStorageValue.clear !== "function") {
    Object.defineProperty(localStorageValue, "clear", {
      value: vi.fn(() => {
        storageState.clear();
      }),
      writable: true,
      configurable: true,
    });
  }

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
