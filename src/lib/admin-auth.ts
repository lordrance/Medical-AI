import { NextResponse } from "next/server";

export function checkAdminToken(req: Request): NextResponse | null {
  const expected = process.env.ADMIN_TOKEN;
  if (!expected) {
    return NextResponse.json(
      { error: "ADMIN_TOKEN not configured on server" },
      { status: 500 },
    );
  }
  const url = new URL(req.url);
  const tokenFromQuery = url.searchParams.get("token");
  const tokenFromHeader = req.headers.get("x-admin-token");
  const token = tokenFromHeader ?? tokenFromQuery;
  if (token !== expected) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return null;
}
