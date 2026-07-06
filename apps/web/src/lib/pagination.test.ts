import { describe, expect, it } from "vitest";
import {
  mergePaginatedItems,
  normalizePaginatedListResponse,
  type PaginatedListResponse,
} from "@/lib/pagination";

describe("pagination helpers", () => {
  it("keeps paginated responses intact", () => {
    const response: PaginatedListResponse<{ id: number }> = {
      items: [{ id: 1 }],
      page: {
        limit: 50,
        offset: 100,
        returned: 1,
        next_offset: null,
        has_more: false,
        total: null,
      },
    };

    expect(normalizePaginatedListResponse(response, 50, 100)).toBe(response);
  });

  it("normalizes legacy arrays into bounded pages", () => {
    const page = normalizePaginatedListResponse(
      [{ id: 1 }, { id: 2 }, { id: 3 }],
      2,
      10,
    );

    expect(page.items).toEqual([{ id: 1 }, { id: 2 }]);
    expect(page.page).toEqual({
      limit: 2,
      offset: 10,
      returned: 2,
      next_offset: 12,
      has_more: true,
      total: null,
    });
  });

  it("merges cached pages without duplicating rows", () => {
    const merged = mergePaginatedItems(
      [
        normalizePaginatedListResponse([{ id: "a" }, { id: "b" }], 2, 0),
        normalizePaginatedListResponse([{ id: "b" }, { id: "c" }], 2, 2),
      ],
      (item) => item.id,
    );

    expect(merged).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }]);
  });
});
