import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/prisma";

const Schema = z.object({
  sessionId: z.string(),
  answers: z.record(z.string(), z.union([z.string(), z.number()])),
});

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const parsed = Schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  const { sessionId, answers } = parsed.data;
  const session = await prisma.session.findUnique({
    where: { id: sessionId },
  });
  if (!session) {
    return NextResponse.json({ error: "Unknown session" }, { status: 404 });
  }

  const yp = answers["years_practice"];
  const af = answers["ai_familiarity"];

  await prisma.participant.update({
    where: { id: session.participantId },
    data: {
      specialty: typeof answers["specialty"] === "string" ? answers["specialty"] : null,
      trainingLevel:
        typeof answers["training_level"] === "string"
          ? (answers["training_level"] as string)
          : null,
      yearsPractice: typeof yp === "number" ? yp : null,
      weeklyMessageVolume:
        typeof answers["weekly_message_volume"] === "string"
          ? (answers["weekly_message_volume"] as string)
          : null,
      priorAiUse:
        typeof answers["prior_ai_use"] === "string"
          ? (answers["prior_ai_use"] as string)
          : null,
      aiFamiliarity: typeof af === "number" ? af : null,
    },
  });

  await prisma.uiEvent.create({
    data: {
      sessionId,
      eventType: "pre_survey_submitted",
      payloadJson: JSON.stringify(answers),
    },
  });

  return NextResponse.json({ ok: true });
}
