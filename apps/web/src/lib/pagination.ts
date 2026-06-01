export type PaginatedListResponse<T> = {
  items: T[];
  page: {
    limit: number;
    offset: number;
    returned: number;
    next_offset: number | null;
    has_more: boolean;
    total?: number | null;
  };
};

export const DASHBOARD_PAGE_SIZE = 50;
export const DASHBOARD_CACHE_STALE_MS = 5 * 60_000;
export const DASHBOARD_CACHE_GC_MS = 15 * 60_000;

export function emptyPaginatedList<T>(limit: number, offset = 0): PaginatedListResponse<T> {
  return {
    items: [],
    page: {
      limit,
      offset,
      returned: 0,
      next_offset: null,
      has_more: false,
      total: null,
    },
  };
}

export function normalizePaginatedListResponse<T>(
  data: PaginatedListResponse<T> | T[] | null | undefined,
  limit: number,
  offset = 0,
): PaginatedListResponse<T> {
  if (
    data &&
    !Array.isArray(data) &&
    Array.isArray(data.items) &&
    data.page
  ) {
    return data;
  }

  const legacyItems = Array.isArray(data) ? data : [];
  const pageItems = legacyItems.slice(0, limit);
  const hasMore = legacyItems.length > limit;
  return {
    items: pageItems,
    page: {
      limit,
      offset,
      returned: pageItems.length,
      next_offset: hasMore ? offset + pageItems.length : null,
      has_more: hasMore,
      total: null,
    },
  };
}

export function mergePaginatedItems<T>(
  pages: Array<PaginatedListResponse<T>> | undefined,
  getKey: (item: T) => string | number,
): T[] {
  const seen = new Set<string | number>();
  const merged: T[] = [];

  for (const page of pages ?? []) {
    for (const item of page.items) {
      const key = getKey(item);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(item);
    }
  }

  return merged;
}
