import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: no session cookie means "go sign in". The API validates
// the session on every request, so a stale cookie still ends up at sign-in.
const SESSION_COOKIE = "relay_session";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/sign-in";
  url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/home/:path*", "/people/:path*", "/handovers/:path*", "/interview/:path*", "/day-one/:path*", "/ask/:path*", "/settings/:path*", "/welcome"],
};
