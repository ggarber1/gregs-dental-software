import { NextResponse } from "next/server";
import { z } from "zod";

import { buildPortalClearCookieHeaders, buildPortalSetCookieHeaders } from "@/lib/auth/cookies";

const SetSessionBody = z.object({
  accessToken: z.string().min(1),
});

export async function POST(req: Request): Promise<NextResponse> {
  const body: unknown = await req.json().catch(() => null);
  const parsed = SetSessionBody.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const headers = buildPortalSetCookieHeaders(parsed.data.accessToken);
  const response = NextResponse.json({ ok: true });
  headers.forEach((header) => response.headers.append("Set-Cookie", header));
  return response;
}

export function DELETE(): NextResponse {
  const headers = buildPortalClearCookieHeaders();
  const response = NextResponse.json({ ok: true });
  headers.forEach((header) => response.headers.append("Set-Cookie", header));
  return response;
}
