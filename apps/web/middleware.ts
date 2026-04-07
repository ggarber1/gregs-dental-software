import { type NextRequest, NextResponse } from "next/server";

import { getAccessTokenFromRequest } from "@/lib/auth/cookies";
import { validateAccessToken } from "@/lib/auth/jwks";

export async function middleware(req: NextRequest): Promise<NextResponse> {
  const { nextUrl } = req;
  const isAuthRoute = nextUrl.pathname.startsWith("/login");

  const token = getAccessTokenFromRequest(req);
  if (!token) {
    console.log(`[middleware] no token cookie on ${nextUrl.pathname}`);
  }
  const payload = token ? await validateAccessToken(token) : null;
  if (token && !payload) {
    console.error(`[middleware] token present but validateAccessToken returned null on ${nextUrl.pathname}`);
  }
  const isAuthenticated = payload !== null;

  if (isAuthRoute) {
    if (isAuthenticated) {
      return NextResponse.redirect(new URL("/dashboard", nextUrl));
    }
    return NextResponse.next();
  }

  if (!isAuthenticated) {
    return NextResponse.redirect(new URL("/login", nextUrl));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!auth|_next/static|_next/image|favicon.ico).*)"],
};
