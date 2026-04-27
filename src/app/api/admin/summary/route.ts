import { NextResponse } from "next/server";
import { checkAdminToken } from "@/lib/admin-auth";
import {
  computeCompletionStats,
  computeConfusionMatrix,
  computePerCaseStats,
  computePerParticipantStats,
} from "@/lib/analysis";

export async function GET(req: Request) {
  const auth = checkAdminToken(req);
  if (auth) return auth;

  const [completion, confusionMatrix, perCase, perParticipant] =
    await Promise.all([
      computeCompletionStats(),
      computeConfusionMatrix(),
      computePerCaseStats(),
      computePerParticipantStats(),
    ]);

  return NextResponse.json({
    completion,
    confusionMatrix,
    perCase,
    perParticipant,
  });
}
