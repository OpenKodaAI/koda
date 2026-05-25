import { describe, expect, it } from "vitest";
import {
  applyReplacement,
  clearTrigger,
  detectTrigger,
} from "@/components/sessions/chat/composer/trigger-detection";

describe("detectTrigger '/'", () => {
  it("activates at the start of the text", () => {
    const m = detectTrigger("/new", 4, "/");
    expect(m).toEqual({ start: 0, end: 4, query: "new" });
  });

  it("activates after a whitespace boundary", () => {
    const text = "Hello /macro";
    const m = detectTrigger(text, text.length, "/");
    expect(m).toEqual({ start: 6, end: 12, query: "macro" });
  });

  it("does not trigger inside a URL", () => {
    const text = "https://example.com/path";
    const m = detectTrigger(text, text.length, "/");
    expect(m).toBeNull();
  });

  it("closes when the user types a space after the trigger", () => {
    const text = "/new session";
    expect(detectTrigger(text, text.length, "/")).toBeNull();
  });

  it("activates at the empty-query boundary right after typing the trigger", () => {
    const m = detectTrigger("/", 1, "/");
    expect(m).toEqual({ start: 0, end: 1, query: "" });
  });
});

describe("detectTrigger '@'", () => {
  it("activates after a whitespace boundary", () => {
    const text = "ping @py";
    const m = detectTrigger(text, text.length, "@");
    expect(m).toEqual({ start: 5, end: 8, query: "py" });
  });

  it("does NOT trigger on an email-like @", () => {
    const text = "ryan@gmail.com";
    expect(detectTrigger(text, text.length, "@")).toBeNull();
  });

  it("activates only at the most-recent valid trigger before the caret", () => {
    const text = "old @bot ping @py";
    const m = detectTrigger(text, text.length, "@");
    expect(m?.query).toBe("py");
    expect(m?.start).toBe(14);
  });

  it("does not activate when caret is past a whitespace", () => {
    const text = "@bot here";
    expect(detectTrigger(text, text.length, "@")).toBeNull();
  });
});

describe("applyReplacement", () => {
  it("inserts replacement at the trigger range and returns the post-caret", () => {
    const text = "Hello /macro";
    const m = detectTrigger(text, text.length, "/")!;
    const out = applyReplacement(text, m, "/macro-deploy ");
    expect(out.text).toBe("Hello /macro-deploy ");
    expect(out.caret).toBe(out.text.length);
  });

  it("preserves text after the trigger range", () => {
    const text = "/m and the rest";
    const m = detectTrigger(text, 2, "/")!;
    const out = applyReplacement(text, m, "/macro ");
    expect(out.text).toBe("/macro  and the rest");
    expect(out.caret).toBe("/macro ".length);
  });
});

describe("clearTrigger", () => {
  it("removes the trigger token entirely", () => {
    const text = "Hello /clear";
    const m = detectTrigger(text, text.length, "/")!;
    const out = clearTrigger(text, m);
    expect(out.text).toBe("Hello ");
    expect(out.caret).toBe(6);
  });
});
