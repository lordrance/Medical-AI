import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { checkAdminToken } from "@/lib/admin-auth";
import { toCsv } from "@/lib/csv";
import {
  computeCompletionStats,
  computeConfusionMatrix,
  computePerCaseStats,
  computePerParticipantStats,
} from "@/lib/analysis";

const TABLES = [
  "participants",
  "sessions",
  "case_presentations",
  "actions",
  "case_surveys",
  "post_surveys",
  "ui_events",
  "summary",
] as const;

type Table = (typeof TABLES)[number];

function isTable(s: string): s is Table {
  return (TABLES as readonly string[]).includes(s);
}

export async function GET(req: Request) {
  const auth = checkAdminToken(req);
  if (auth) return auth;

  const url = new URL(req.url);
  const format = (url.searchParams.get("format") ?? "csv").toLowerCase();
  const table = url.searchParams.get("table") ?? "summary";
  if (format !== "csv" && format !== "json") {
    return NextResponse.json({ error: "format must be csv or json" }, { status: 400 });
  }
  if (!isTable(table)) {
    return NextResponse.json(
      { error: `unknown table; allowed: ${TABLES.join(", ")}` },
      { status: 400 },
    );
  }

  const rows = await loadTable(table);

  if (format === "json") {
    return NextResponse.json(rows, {
      headers: {
        "Content-Disposition": `attachment; filename="${table}.json"`,
      },
    });
  }

  // For summary in CSV format, we flatten reasonably.
  const flatRows = Array.isArray(rows)
    ? rows
    : flattenSummary(rows as SummaryShape);
  const csv = toCsv(flatRows as Record<string, unknown>[]);
  return new Response(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${table}.csv"`,
    },
  });
}

interface SummaryShape {
  completion: Awaited<ReturnType<typeof computeCompletionStats>>;
  confusionMatrix: Awaited<ReturnType<typeof computeConfusionMatrix>>;
  perCase: Awaited<ReturnType<typeof computePerCaseStats>>;
  perParticipant: Awaited<ReturnType<typeof computePerParticipantStats>>;
}

async function loadTable(table: Table): Promise<unknown> {
  switch (table) {
    case "participants": {
      const rows = await prisma.participant.findMany();
      return rows.map((r) => ({
        participantId: r.id,
        condition: r.condition,
        orderTemplateId: r.orderTemplateId,
        specialty: r.specialty,
        trainingLevel: r.trainingLevel,
        yearsPractice: r.yearsPractice,
        weeklyMessageVolume: r.weeklyMessageVolume,
        priorAiUse: r.priorAiUse,
        aiFamiliarity: r.aiFamiliarity,
        startedAt: r.startedAt.toISOString(),
        completedAt: r.completedAt?.toISOString() ?? null,
        completedFlag: r.completedFlag,
      }));
    }
    case "sessions": {
      const rows = await prisma.session.findMany();
      return rows.map((r) => ({
        sessionId: r.id,
        participantId: r.participantId,
        status: r.status,
        startedAt: r.startedAt.toISOString(),
        endedAt: r.endedAt?.toISOString() ?? null,
      }));
    }
    case "case_presentations": {
      const rows = await prisma.casePresentation.findMany({
        include: { case: true, session: true },
      });
      return rows.map((r) => ({
        casePresentationId: r.id,
        sessionId: r.sessionId,
        participantId: r.session.participantId,
        caseId: r.caseId,
        isPractice: r.case.isPractice,
        riskLevel: r.case.riskLevel,
        defectPresent: r.case.defectPresent,
        defectType: r.case.defectType,
        orderIndex: r.orderIndex,
        startedAt: r.startedAt.toISOString(),
        endedAt: r.endedAt?.toISOString() ?? null,
        durationMs: r.durationMs,
      }));
    }
    case "actions": {
      const rows = await prisma.action.findMany({
        include: {
          casePresentation: { include: { case: true, session: true } },
        },
      });
      return rows.map((r) => {
        const c = r.casePresentation.case;
        const goldAlternates: string[] = c.goldActionAlternates
          ? (JSON.parse(c.goldActionAlternates) as string[])
          : [];
        const goldMatch =
          r.selectedAction === c.goldAction ||
          goldAlternates.includes(r.selectedAction);
        return {
          actionId: r.id,
          casePresentationId: r.casePresentationId,
          sessionId: r.casePresentation.sessionId,
          participantId: r.casePresentation.session.participantId,
          caseId: r.casePresentation.caseId,
          orderIndex: r.casePresentation.orderIndex,
          selectedAction: r.selectedAction,
          sendAsIsFlag: r.sendAsIsFlag,
          editFlag: r.editFlag,
          discardFlag: r.discardFlag,
          escalateFlag: r.escalateFlag,
          escalateSubtype: r.escalateSubtype,
          finalReplyText: r.finalReplyText,
          finalReplyCharCount: r.finalReplyCharCount,
          editDistance: r.editDistance,
          goldAction: c.goldAction,
          goldActionMatch: goldMatch,
          clientStatsJson: r.clientStatsJson,
          serverReceivedAt: r.serverReceivedAt.toISOString(),
        };
      });
    }
    case "case_surveys": {
      const rows = await prisma.caseSurvey.findMany({
        include: { casePresentation: { include: { session: true } } },
      });
      return rows.map((r) => ({
        caseSurveyId: r.id,
        casePresentationId: r.casePresentationId,
        sessionId: r.casePresentation.sessionId,
        participantId: r.casePresentation.session.participantId,
        caseId: r.casePresentation.caseId,
        safeToSend: r.safeToSend,
        confidenceInJudgment: r.confidenceInJudgment,
        aiDraftHelpful: r.aiDraftHelpful,
        serverReceivedAt: r.serverReceivedAt.toISOString(),
      }));
    }
    case "post_surveys": {
      const rows = await prisma.postSurvey.findMany();
      return rows.map((r) => ({
        postSurveyId: r.id,
        sessionId: r.sessionId,
        participantId: r.participantId,
        payloadJson: r.payloadJson,
        serverReceivedAt: r.serverReceivedAt.toISOString(),
      }));
    }
    case "ui_events": {
      const rows = await prisma.uiEvent.findMany({
        orderBy: { serverTs: "asc" },
      });
      return rows.map((r) => ({
        uiEventId: r.id,
        sessionId: r.sessionId,
        casePresentationId: r.casePresentationId,
        eventType: r.eventType,
        payloadJson: r.payloadJson,
        clientTs: r.clientTs?.toISOString() ?? null,
        serverTs: r.serverTs.toISOString(),
      }));
    }
    case "summary": {
      const [completion, confusionMatrix, perCase, perParticipant] =
        await Promise.all([
          computeCompletionStats(),
          computeConfusionMatrix(),
          computePerCaseStats(),
          computePerParticipantStats(),
        ]);
      return { completion, confusionMatrix, perCase, perParticipant };
    }
  }
}

function flattenSummary(s: SummaryShape) {
  const cmRows = s.confusionMatrix.actions.flatMap((gold, gi) =>
    s.confusionMatrix.actions.map((sel, si) => ({
      kind: "confusion_matrix",
      goldAction: gold,
      selectedAction: sel,
      count: s.confusionMatrix.matrix[gi][si],
    })),
  );
  const perCase = s.perCase.map((c) => ({ kind: "per_case", ...c }));
  const perPt = s.perParticipant.map((p) => ({ kind: "per_participant", ...p }));
  const completion = [
    {
      kind: "completion",
      totalParticipants: s.completion.totalParticipants,
      completed: s.completion.completed,
      completionRate: s.completion.completionRate,
      byCondition: JSON.stringify(s.completion.byCondition),
      accuracy: s.confusionMatrix.accuracy,
      totalActions: s.confusionMatrix.total,
    },
  ];
  return [...completion, ...cmRows, ...perCase, ...perPt];
}
