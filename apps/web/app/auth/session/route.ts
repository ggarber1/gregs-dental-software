import { NextResponse } from "next/server";
import { z } from "zod";

import { buildClearCookieHeaders, buildSetCookieHeaders } from "@/lib/auth/cookies";

const SetSessionBody = z.object({
  accessToken: z.string().min(1),
  refreshToken: z.string().optional(),
});

// Called by the login page after Amplify sign-in succeeds.
// Stores the Cognito tokens in cookies so middleware and server components can read them.
export async function POST(req: Request): Promise<NextResponse> {
  const body: unknown = await req.json().catch(() => null);
  const parsed = SetSessionBody.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const { accessToken, refreshToken } = parsed.data;
  const headers = buildSetCookieHeaders(accessToken, refreshToken);

  const response = NextResponse.json({ ok: true });
  headers.forEach((header) => response.headers.append("Set-Cookie", header));
  return response;
}

// Called on sign-out. Clears both session cookies.
export function DELETE(): NextResponse {
  const headers = buildClearCookieHeaders();
  const response = NextResponse.json({ ok: true });
  headers.forEach((header) => response.headers.append("Set-Cookie", header));
  return response;
}
