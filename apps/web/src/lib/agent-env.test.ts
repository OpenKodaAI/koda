import { describe, expect, it } from "vitest";
import { parseDotenv, resolveScopedEnvValue } from "@/lib/agent-env";

describe("agent-env", () => {
  it("parses dotenv content with comments, exports and quotes", () => {
    const values = parseDotenv(`
      # comment
      export BOT_ID=ATLAS
      RUNTIME_LOCAL_UI_TOKEN="secret-token"
      ORBITAL_ONE_RUNTIME_LOCAL_UI_TOKEN='scoped-token'
    `);

    expect(values.BOT_ID).toBe("ATLAS");
    expect(values.RUNTIME_LOCAL_UI_TOKEN).toBe("secret-token");
    expect(values.ORBITAL_ONE_RUNTIME_LOCAL_UI_TOKEN).toBe("scoped-token");
  });

  it("prefers agent scoped keys and falls back to shared ones", () => {
    const values = {
      RUNTIME_LOCAL_UI_TOKEN: "shared-token",
      ATLAS_RUNTIME_LOCAL_UI_TOKEN: "masp-token",
    };

    expect(resolveScopedEnvValue(values, "ATLAS", "RUNTIME_LOCAL_UI_TOKEN")).toBe(
      "masp-token"
    );
    expect(resolveScopedEnvValue(values, "NOVA", "RUNTIME_LOCAL_UI_TOKEN")).toBe(
      "shared-token"
    );
  });
});
