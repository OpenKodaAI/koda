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
  request:
    | Request
    | {
        url?: string;
        nextUrl?: URL;
        headers?: Headers | { get(name: string): string | null | undefined };
      },
): string | null {
  // Prefer the Host header: it reflects the hostname the client actually
  // contacted. When the server is bound to 0.0.0.0 but the browser reached it
  // as 127.0.0.1 or localhost, `request.nextUrl.origin` reports the bind
  // address and no browser Origin will ever match it.
  const hostHeader = getHeader(request, "host");
  if (hostHeader) {
    const forwardedProto = getHeader(request, "x-forwarded-proto");
    let proto = forwardedProto ? forwardedProto.split(",")[0].trim() : "";
    if (!proto) {
      if ("nextUrl" in request && request.nextUrl instanceof URL) {
        proto = request.nextUrl.protocol.replace(":", "");
      } else if ("url" in request && typeof request.url === "string") {
        try {
          proto = new URL(request.url).protocol.replace(":", "");
        } catch {
          proto = "";
        }
      }
    }
    if (!proto) {
      proto = "http";
    }
    return `${proto}://${hostHeader}`;
  }

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
