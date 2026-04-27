import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(
  req: Request,
  { params }: { params: { caseId: string } },
) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get("sessionId");
  if (!sessionId) {
    return NextResponse.json({ error: "Missing sessionId" }, { status: 400 });
  }
  const session = await prisma.session.findUnique({
    where: { id: sessionId },
    include: { participant: true },
  });
  if (!session) {
    return NextResponse.json({ error: "Unknown session" }, { status: 404 });
  }

  const c = await prisma.case.findUnique({ where: { id: params.caseId } });
  if (!c) {
    return NextResponse.json({ error: "Case not found" }, { status: 404 });
  }

  const condition = session.participant.condition;
  const isGuardrail = condition === "guardrail";

  return NextResponse.json({
    case: {
      id: c.id,
      isPractice: c.isPractice,
      riskLevel: c.riskLevel,
      patientMessage: c.patientMessage,
      chartSnapshot: JSON.parse(c.chartSnapshotJson),
      aiDraft: c.aiDraft,
      guardrail: isGuardrail
        ? {
            factsUsed: JSON.parse(c.factsUsedJson),
            riskCue: c.riskCue,
            checklist: JSON.parse(c.checklistJson),
          }
        : undefined,
    },
  });
}
