// @vitest-environment node

import { describe, expect, it } from "vitest";
import nextConfig from "../../next.config";

describe("next.config", () => {
  // Every next/image in the app is an SVG, which next/image never sends to the
  // optimizer, or is marked unoptimized. With the optimizer off, /_next/image
  // answers 404 before it parses a URL or loads sharp.
  it("turns the image optimizer off", () => {
    expect(nextConfig.images?.unoptimized).toBe(true);
  });
});
