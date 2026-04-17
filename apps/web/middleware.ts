import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "koda_operator_session";
const SETUP_PATH = "/setup";

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

  // Not authenticated → force /setup unless already there
  if (!hasSession && !isSetupRoute) {
    const url = request.nextUrl.clone();
    url.pathname = SETUP_PATH;
    url.search = "";
    return NextResponse.redirect(url);
  }

  // Already authenticated → don't allow revisiting /setup (the setup page itself
  // will still redirect to /setup if onboarding_complete === false after bootstrap)
  if (hasSession && pathname === SETUP_PATH) {
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
