import { NextRequest, NextResponse } from "next/server";

const WEB_OPERATOR_SESSION_COOKIE = "koda_operator_session";

function unauthorizedResponse(message: string) {
  return NextResponse.json(
    { error: message },
    {
      status: 401,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/api/control-plane/web-auth") {
    return NextResponse.next();
  }

  const cookie = request.cookies.get(WEB_OPERATOR_SESSION_COOKIE)?.value?.trim();
  if (!cookie) {
    return unauthorizedResponse("Operator session is required.");
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/api/control-plane/:path*", "/api/runtime/:path*"],
};
