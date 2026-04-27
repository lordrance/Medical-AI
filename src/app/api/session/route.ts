import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { assignCondition, pickOrderTemplateId } from "@/lib/randomization";

export async function POST() {
  const templates = await prisma.orderTemplate.findMany();
  if (templates.length === 0) {
    return NextResponse.json(
      { error: "No order templates seeded" },
      { status: 500 },
    );
  }
  const orderTemplateId = pickOrderTemplateId(templates.map((t) => t.id));
  const tpl = templates.find((t) => t.id === orderTemplateId)!;
  const caseOrder: string[] = JSON.parse(tpl.orderJson);

  const condition = assignCondition();

  const practice = await prisma.case.findFirst({ where: { isPractice: true } });
  if (!practice) {
    return NextResponse.json({ error: "Practice case missing" }, { status: 500 });
  }

  const participant = await prisma.participant.create({
    data: {
      condition,
      orderTemplateId,
    },
  });
  const session = await prisma.session.create({
    data: { participantId: participant.id },
  });

  await prisma.uiEvent.create({
    data: {
      sessionId: session.id,
      eventType: "session_started",
      payloadJson: JSON.stringify({ condition, orderTemplateId }),
    },
  });

  return NextResponse.json({
    sessionId: session.id,
    participantId: participant.id,
    condition,
    orderTemplateId,
    caseOrder,
    practiceCaseId: practice.id,
  });
}
