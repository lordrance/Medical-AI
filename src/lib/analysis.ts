import { prisma } from "./prisma";
import { ALL_ACTIONS, type SelectedAction } from "./types";

export interface ConfusionMatrixCell {
  goldAction: SelectedAction;
  selectedAction: SelectedAction;
  count: number;
}

export interface ConfusionMatrix {
  actions: SelectedAction[];
  matrix: number[][];
  total: number;
  accuracy: number;
}

export interface PerCaseStat {
  caseId: string;
  defectPresent: boolean;
  riskLevel: string;
  goldAction: SelectedAction;
  goldActionAlternates: SelectedAction[];
  total: number;
  matchGold: number;
  matchAlternates: number;
  unsafeSendAsIs: number;
  errorSurvival: number;
  appropriateEscalation: number;
  meanDurationMs: number;
  meanEditDistance: number;
}

export interface PerParticipantStat {
  participantId: string;
  condition: string;
  total: number;
  matchGold: number;
  accuracy: number;
  errorSurvivalCount: number;
  appropriateEscalationCount: number;
  meanDurationMs: number;
  meanEditDistance: number;
}

interface PresentationWithRel {
  id: string;
  caseId: string;
  orderIndex: number;
  durationMs: number | null;
  case: {
    id: string;
    isPractice: boolean;
    defectPresent: boolean;
    riskLevel: string;
    goldAction: string;
    goldActionAlternates: string | null;
  };
  action: {
    selectedAction: string;
    sendAsIsFlag: boolean;
    escalateFlag: boolean;
    editDistance: number | null;
  } | null;
  session: {
    participantId: string;
    participant: {
      condition: string;
    };
  };
}

function isAction(s: string): s is SelectedAction {
  return ALL_ACTIONS.includes(s as SelectedAction);
}

async function loadFormalPresentations(): Promise<PresentationWithRel[]> {
  const rows = await prisma.casePresentation.findMany({
    include: {
      case: true,
      action: true,
      session: { include: { participant: true } },
    },
  });
  return rows.filter((r) => !r.case.isPractice && r.action != null) as PresentationWithRel[];
}

export async function computeConfusionMatrix(): Promise<ConfusionMatrix> {
  const rows = await loadFormalPresentations();
  const actions = ALL_ACTIONS;
  const idx = new Map(actions.map((a, i) => [a, i] as const));
  const matrix: number[][] = actions.map(() => actions.map(() => 0));
  let correct = 0;
  let total = 0;
  for (const r of rows) {
    if (!r.action) continue;
    const gold = r.case.goldAction;
    const sel = r.action.selectedAction;
    if (!isAction(gold) || !isAction(sel)) continue;
    matrix[idx.get(gold)!][idx.get(sel)!] += 1;
    total += 1;
    if (gold === sel) correct += 1;
  }
  return {
    actions,
    matrix,
    total,
    accuracy: total > 0 ? correct / total : 0,
  };
}

export async function computePerCaseStats(): Promise<PerCaseStat[]> {
  const rows = await loadFormalPresentations();

  const byCase = new Map<string, PresentationWithRel[]>();
  for (const r of rows) {
    if (!byCase.has(r.caseId)) byCase.set(r.caseId, []);
    byCase.get(r.caseId)!.push(r);
  }

  const stats: PerCaseStat[] = [];
  for (const [caseId, group] of byCase.entries()) {
    const c = group[0].case;
    const alternates: SelectedAction[] = c.goldActionAlternates
      ? (JSON.parse(c.goldActionAlternates) as string[]).filter(isAction)
      : [];
    const gold = isAction(c.goldAction) ? c.goldAction : "send_as_is";

    let matchGold = 0;
    let matchAlt = 0;
    let unsafeSendAsIs = 0;
    let errorSurvival = 0;
    let appropriateEscalation = 0;
    let durSum = 0;
    let durN = 0;
    let edSum = 0;
    let edN = 0;

    for (const p of group) {
      if (!p.action) continue;
      const sel = p.action.selectedAction;
      if (sel === gold) matchGold += 1;
      if (alternates.includes(sel as SelectedAction)) matchAlt += 1;
      if (c.defectPresent && p.action.sendAsIsFlag) unsafeSendAsIs += 1;
      if (c.defectPresent && sel !== gold && !alternates.includes(sel as SelectedAction)) {
        errorSurvival += 1;
      }
      if (gold === "escalate" && p.action.escalateFlag) appropriateEscalation += 1;
      if (typeof p.durationMs === "number") {
        durSum += p.durationMs;
        durN += 1;
      }
      if (typeof p.action.editDistance === "number") {
        edSum += p.action.editDistance;
        edN += 1;
      }
    }

    stats.push({
      caseId,
      defectPresent: c.defectPresent,
      riskLevel: c.riskLevel,
      goldAction: gold,
      goldActionAlternates: alternates,
      total: group.length,
      matchGold,
      matchAlternates: matchAlt,
      unsafeSendAsIs,
      errorSurvival,
      appropriateEscalation,
      meanDurationMs: durN > 0 ? durSum / durN : 0,
      meanEditDistance: edN > 0 ? edSum / edN : 0,
    });
  }
  stats.sort((a, b) => a.caseId.localeCompare(b.caseId));
  return stats;
}

export async function computePerParticipantStats(): Promise<PerParticipantStat[]> {
  const rows = await loadFormalPresentations();
  const byPt = new Map<string, PresentationWithRel[]>();
  for (const r of rows) {
    const pid = r.session.participantId;
    if (!byPt.has(pid)) byPt.set(pid, []);
    byPt.get(pid)!.push(r);
  }
  const stats: PerParticipantStat[] = [];
  for (const [participantId, group] of byPt.entries()) {
    let matchGold = 0;
    let total = 0;
    let errorSurvival = 0;
    let appropriateEscalation = 0;
    let durSum = 0;
    let durN = 0;
    let edSum = 0;
    let edN = 0;
    const condition = group[0].session.participant.condition;
    for (const p of group) {
      if (!p.action) continue;
      total += 1;
      const gold = p.case.goldAction;
      const sel = p.action.selectedAction;
      const alternates: string[] = p.case.goldActionAlternates
        ? (JSON.parse(p.case.goldActionAlternates) as string[])
        : [];
      if (sel === gold) matchGold += 1;
      if (
        p.case.defectPresent &&
        sel !== gold &&
        !alternates.includes(sel)
      ) {
        errorSurvival += 1;
      }
      if (gold === "escalate" && p.action.escalateFlag) {
        appropriateEscalation += 1;
      }
      if (typeof p.durationMs === "number") {
        durSum += p.durationMs;
        durN += 1;
      }
      if (typeof p.action.editDistance === "number") {
        edSum += p.action.editDistance;
        edN += 1;
      }
    }
    stats.push({
      participantId,
      condition,
      total,
      matchGold,
      accuracy: total > 0 ? matchGold / total : 0,
      errorSurvivalCount: errorSurvival,
      appropriateEscalationCount: appropriateEscalation,
      meanDurationMs: durN > 0 ? durSum / durN : 0,
      meanEditDistance: edN > 0 ? edSum / edN : 0,
    });
  }
  stats.sort((a, b) => a.participantId.localeCompare(b.participantId));
  return stats;
}

export async function computeCompletionStats() {
  const totalParticipants = await prisma.participant.count();
  const completed = await prisma.participant.count({
    where: { completedFlag: true },
  });
  const byCondition = await prisma.participant.groupBy({
    by: ["condition"],
    _count: { _all: true },
  });
  return {
    totalParticipants,
    completed,
    completionRate:
      totalParticipants > 0 ? completed / totalParticipants : 0,
    byCondition: byCondition.map((b) => ({
      condition: b.condition,
      count: b._count._all,
    })),
  };
}
