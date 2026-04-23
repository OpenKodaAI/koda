import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "koda_operator_session";
const SETUP_PATH = "/setup";
const AUTH_ROUTES = ["/login", "/forgot-password"];

function isPublicPath(pathname: string): boolean {
  return (
    pathname.startsWith("/api/") ||
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/oauth/") ||
    pathname === "/favicon.ico" ||
    pathname === "/robots.txt" ||
    pathname === "/sitemap.xml" ||
    pathname.startsWith("/apple-icon") ||
    pathname.startsWith("/icon") ||
    pathname.endsWith(".svg") ||
    pathname.endsWith(".png") ||
    pathname.endsWith(".webp")
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  const isSetupRoute = pathname === SETUP_PATH || pathname.startsWith(`${SETUP_PATH}/`);
  const isAuthRoute = AUTH_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );

  // Not authenticated → force /setup unless already on setup or an auth page.
  // /login and /forgot-password decide themselves whether to redirect to /setup
  // (when no owner exists yet) or to render their form.
  if (!hasSession && !isSetupRoute && !isAuthRoute) {
    const url = request.nextUrl.clone();
    url.pathname = SETUP_PATH;
    url.search = "";
    return NextResponse.redirect(url);
  }

  // Already authenticated → don't allow revisiting /setup or auth pages (the
  // setup page itself will still redirect to /setup if onboarding_complete ===
  // false after bootstrap).
  if (hasSession && (pathname === SETUP_PATH || isAuthRoute)) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|_next/webpack-hmr|favicon.ico|apple-icon.png|robots.txt|sitemap.xml).*)",
  ],
};
