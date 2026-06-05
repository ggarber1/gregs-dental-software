import { type NextRequest, NextResponse } from "next/server";

import {
  getAccessTokenFromRequest,
  getPortalAccessTokenFromRequest,
} from "@/lib/auth/cookies";
import { validateAccessToken } from "@/lib/auth/jwks";
import { isPortalAuthConfigured, validatePortalAccessToken } from "@/lib/auth/portal-jwks";

function isPortalPublicPath(pathname: string): boolean {
  return pathname.startsWith("/portal/login") || pathname.startsWith("/portal/accept/");
}

function isPortalPath(pathname: string): boolean {
  return pathname === "/portal" || pathname.startsWith("/portal/");
}

export async function middleware(req: NextRequest): Promise<NextResponse> {
  const { nextUrl } = req;
  const pathname = nextUrl.pathname;

  if (pathname.startsWith("/intake")) {
    return NextResponse.next();
  }

  if (isPortalPath(pathname)) {
    if (pathname.startsWith("/portal/auth/")) {
      return NextResponse.next();
    }

    if (isPortalPublicPath(pathname)) {
      return NextResponse.next();
    }

    if (!isPortalAuthConfigured()) {
      if (pathname === "/portal") {
        return NextResponse.redirect(new URL("/portal/login", nextUrl));
      }
      return NextResponse.next();
    }

    const portalToken = getPortalAccessTokenFromRequest(req);
    const portalPayload = portalToken ? await validatePortalAccessToken(portalToken) : null;

    if (!portalPayload) {
      return NextResponse.redirect(new URL("/portal/login", nextUrl));
    }

    if (pathname === "/portal/login") {
      return NextResponse.redirect(new URL("/portal", nextUrl));
    }

    return NextResponse.next();
  }

  const isAuthRoute = pathname.startsWith("/login");
  const token = getAccessTokenFromRequest(req);
  const payload = token ? await validateAccessToken(token) : null;
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
