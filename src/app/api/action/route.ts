import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";

const ActionEnum = z.enum([
  "send_as_is",
  "edit_then_send",
  "discard_and_rewrite",
  "escalate",
]);

const Schema = z.object({
  sessionId: z.string(),
  caseId: z.string(),
  orderIndex: z.number().int(),
  isPractice: z.boolean().optional(),
  selectedAction: ActionEnum,
  finalReplyText: z.string(),
  escalateSubtype: z.string().optional(),
  quickSurvey: z.object({
    item1: z.number().int().min(1).max(7),
    item2: z.number().int().min(1).max(7),
    item3: z.number().int().min(1).max(7),
  }),
  timing: z.object({
    startedAt: z.number(),
    endedAt: z.number(),
    durationMs: z.number().int().nonnegative(),
  }),
});

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const parsed = Schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  const data = parsed.data;

  const session = await prisma.session.findUnique({
    where: { id: data.sessionId },
  });
  if (!session) {
    return NextResponse.json({ error: "Unknown session" }, { status: 404 });
  }

  const presentation = await prisma.casePresentation.create({
    data: {
      sessionId: data.sessionId,
      caseId: data.caseId,
      orderIndex: data.orderIndex,
      startedAt: new Date(data.timing.startedAt),
      endedAt: new Date(data.timing.endedAt),
      durationMs: data.timing.durationMs,
    },
  });

  await prisma.action.create({
    data: {
      casePresentationId: presentation.id,
      selectedAction: data.selectedAction,
      sendAsIsFlag: data.selectedAction === "send_as_is",
      editFlag: data.selectedAction === "edit_then_send",
      discardFlag: data.selectedAction === "discard_and_rewrite",
      escalateFlag: data.selectedAction === "escalate",
      escalateSubtype: data.escalateSubtype ?? null,
      finalReplyText: data.finalReplyText,
      finalReplyCharCount: data.finalReplyText.length,
    },
  });

  await prisma.caseSurvey.create({
    data: {
      casePresentationId: presentation.id,
      safeToSend: data.quickSurvey.item1,
      confidenceInJudgment: data.quickSurvey.item2,
      aiDraftHelpful: data.quickSurvey.item3,
    },
  });

  return NextResponse.json({ ok: true, casePresentationId: presentation.id });
}
