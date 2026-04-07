function getHeader(
  request: Request | { headers?: Headers | { get(name: string): string | null | undefined } },
  name: string,
): string | null {
  const headers = request.headers;
  if (!headers || typeof headers.get !== "function") {
    return null;
  }
  const value = headers.get(name);
  return typeof value === "string" ? value : null;
}

function getRequestOrigin(
  request: Request | { url?: string; nextUrl?: URL },
): string | null {
  if ("nextUrl" in request && request.nextUrl instanceof URL) {
    return request.nextUrl.origin;
  }
  if ("url" in request && typeof request.url === "string") {
    try {
      return new URL(request.url).origin;
    } catch {
      return null;
    }
  }
  return null;
}

export function isMutationMethod(method: string | null | undefined): boolean {
  const normalized = String(method || "GET").trim().toUpperCase();
  return !["GET", "HEAD", "OPTIONS"].includes(normalized);
}

export function isTrustedDashboardRequest(
  request: Request | { method?: string; url?: string; nextUrl?: URL; headers?: Headers | { get(name: string): string | null | undefined } },
): boolean {
  if (!isMutationMethod("method" in request ? request.method : undefined)) {
    return true;
  }

  const expectedOrigin = getRequestOrigin(request);
  if (!expectedOrigin) {
    return false;
  }

  for (const headerName of ["origin", "referer"]) {
    const raw = getHeader(request, headerName);
    if (!raw) {
      continue;
    }
    try {
      if (new URL(raw).origin === expectedOrigin) {
        return true;
      }
    } catch {
      return false;
    }
  }

  return false;
}
