import { afterEach, describe, expect, it, vi } from "vitest";

import { formatRetryWait, parseRetryAfterSeconds } from "@/lib/retry-after";

describe("parseRetryAfterSeconds", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("reads delta-seconds, the form the control plane and the dashboard proxy send", () => {
    expect(parseRetryAfterSeconds("60")).toBe(60);
    expect(parseRetryAfterSeconds(" 120 ")).toBe(120);
    expect(parseRetryAfterSeconds("0")).toBe(0);
  });

  it("reads an HTTP-date as the seconds left until it, rounded up", () => {
    vi.useFakeTimers({ now: Date.UTC(2026, 10, 14, 12, 0, 0, 250), toFake: ["Date"] });

    expect(parseRetryAfterSeconds("Sat, 14 Nov 2026 12:02:00 GMT")).toBe(120);
    // A date already in the past means the client may retry now.
    expect(parseRetryAfterSeconds("Sat, 14 Nov 2026 11:59:00 GMT")).toBe(0);
  });

  // `Date.parse` alone would read "1.5", "-5" and "a 1" as dates.
  it.each([null, undefined, "", "   ", "-5", "1.5", "60s", "soon", "a 1", "14 Nov 2026 12:02:00", "99999999999999999999"])(
    "ignores %j",
    (value) => {
      expect(parseRetryAfterSeconds(value)).toBeNull();
    },
  );
});

describe("formatRetryWait", () => {
  // ICU separates some units with a no-break space (French seconds use U+00A0).
  const wait = (seconds: number, language: string) =>
    formatRetryWait(seconds, language).replace(/\s/g, " ");

  it("uses whole minutes, rounded up, from one minute on", () => {
    expect(wait(60, "en-US")).toBe("1 minute");
    expect(wait(61, "en-US")).toBe("2 minutes");
    expect(wait(360, "pt-BR")).toBe("6 minutos");
    expect(wait(120, "de-DE")).toBe("2 Minuten");
  });

  it("uses seconds under a minute", () => {
    expect(wait(1, "en-US")).toBe("1 second");
    expect(wait(30, "fr-FR")).toBe("30 secondes");
    expect(wait(45, "es-ES")).toBe("45 segundos");
  });
});
