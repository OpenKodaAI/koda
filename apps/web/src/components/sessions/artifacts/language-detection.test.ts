import { describe, expect, it } from "vitest";
import { detectLanguage } from "@/components/sessions/artifacts/language-detection";

describe("detectLanguage", () => {
  it("maps known TypeScript extensions", () => {
    expect(detectLanguage("agent.ts")).toBe("typescript");
    expect(detectLanguage("App.tsx")).toBe("typescript");
  });

  it("maps Python extensions", () => {
    expect(detectLanguage("hello.py")).toBe("python");
  });

  it("maps shell variants to bash", () => {
    expect(detectLanguage("setup.sh")).toBe("bash");
    expect(detectLanguage("post-install.zsh")).toBe("bash");
  });

  it("recognises Dockerfile by name", () => {
    expect(detectLanguage("Dockerfile")).toBe("dockerfile");
    expect(detectLanguage("services/api/Dockerfile")).toBe("dockerfile");
  });

  it("falls back to 'plaintext' for unknown or no extension", () => {
    expect(detectLanguage("README")).toBe("plaintext");
    expect(detectLanguage("notes.bin")).toBe("plaintext");
    expect(detectLanguage(null)).toBe("plaintext");
    expect(detectLanguage(undefined)).toBe("plaintext");
  });
});
