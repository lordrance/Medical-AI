import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(req: Request) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Bad JSON" }, { status: 400 });
  }
  if (!body?.sessionId || !body?.eventType) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }
  try {
    await prisma.uiEvent.create({
      data: {
        sessionId: String(body.sessionId),
        casePresentationId: body.casePresentationId
          ? String(body.casePresentationId)
          : null,
        eventType: String(body.eventType),
        payloadJson: body.payload ? JSON.stringify(body.payload) : null,
        clientTs: body.clientTs ? new Date(body.clientTs) : null,
      },
    });
  } catch {
    // Don't break the UI on log failures
  }
  return NextResponse.json({ ok: true });
}
