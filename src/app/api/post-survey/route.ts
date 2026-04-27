import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";

const Schema = z.object({
  sessionId: z.string(),
  payload: z.record(z.string(), z.union([z.string(), z.number()])),
});

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const parsed = Schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  const { sessionId, payload } = parsed.data;
  const session = await prisma.session.findUnique({ where: { id: sessionId } });
  if (!session) {
    return NextResponse.json({ error: "Unknown session" }, { status: 404 });
  }

  await prisma.postSurvey.create({
    data: {
      participantId: session.participantId,
      sessionId,
      payloadJson: JSON.stringify(payload),
    },
  });

  const now = new Date();
  await prisma.session.update({
    where: { id: sessionId },
    data: { status: "completed", endedAt: now },
  });
  await prisma.participant.update({
    where: { id: session.participantId },
    data: { completedFlag: true, completedAt: now },
  });

  return NextResponse.json({ ok: true });
}
