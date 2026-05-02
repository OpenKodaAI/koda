import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// The shader-based agent orb (apps/web/src/components/ui/orb.tsx) uses
// react-three-fiber's <Canvas>, which hits ResizeObserver and a real WebGL
// context — neither exists in jsdom. Mocking the module keeps every test
// that mounts an agent surface (switcher, sigil, glyph) from crashing on a
// rendering concern unrelated to the test's behavior.
vi.mock("@/components/ui/orb", () => ({
  Orb: () => null,
}));

if (typeof window !== "undefined") {
  if (typeof window.ResizeObserver === "undefined") {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    Object.defineProperty(window, "ResizeObserver", {
      value: ResizeObserverStub,
      writable: true,
      configurable: true,
    });
  }
}

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
