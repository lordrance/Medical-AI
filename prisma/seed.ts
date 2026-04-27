import { PrismaClient } from "@prisma/client";
import fs from "node:fs";
import path from "node:path";

const prisma = new PrismaClient();

const dataDir = path.resolve(process.cwd(), "data");

function readJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(path.join(dataDir, file), "utf-8")) as T;
}

interface CaseRecord {
  id: string;
  isPractice: boolean;
  riskLevel: string;
  defectPresent: boolean;
  defectType: string | null;
  purpose?: string;
  patientMessage: string;
  chartSnapshot: Record<string, unknown>;
  aiDraft: string;
  guardrail: {
    factsUsed: string[];
    riskCue: string;
    checklist: string[];
  };
  goldAction: string;
  goldActionAlternates?: string[];
}

interface OrderTemplatesFile {
  templates: { id: number; order: string[] }[];
}

async function main() {
  const cases = readJson<CaseRecord[]>("cases.json");
  const orderTemplates = readJson<OrderTemplatesFile>("order_templates.json");

  console.log(`[seed] cases: ${cases.length}`);
  console.log(`[seed] order templates: ${orderTemplates.templates.length}`);

  for (const c of cases) {
    await prisma.case.upsert({
      where: { id: c.id },
      update: {
        isPractice: c.isPractice,
        riskLevel: c.riskLevel,
        defectPresent: c.defectPresent,
        defectType: c.defectType ?? null,
        purpose: c.purpose ?? null,
        patientMessage: c.patientMessage,
        chartSnapshotJson: JSON.stringify(c.chartSnapshot),
        aiDraft: c.aiDraft,
        factsUsedJson: JSON.stringify(c.guardrail.factsUsed),
        riskCue: c.guardrail.riskCue,
        checklistJson: JSON.stringify(c.guardrail.checklist),
        goldAction: c.goldAction,
        goldActionAlternates: c.goldActionAlternates
          ? JSON.stringify(c.goldActionAlternates)
          : null,
      },
      create: {
        id: c.id,
        isPractice: c.isPractice,
        riskLevel: c.riskLevel,
        defectPresent: c.defectPresent,
        defectType: c.defectType ?? null,
        purpose: c.purpose ?? null,
        patientMessage: c.patientMessage,
        chartSnapshotJson: JSON.stringify(c.chartSnapshot),
        aiDraft: c.aiDraft,
        factsUsedJson: JSON.stringify(c.guardrail.factsUsed),
        riskCue: c.guardrail.riskCue,
        checklistJson: JSON.stringify(c.guardrail.checklist),
        goldAction: c.goldAction,
        goldActionAlternates: c.goldActionAlternates
          ? JSON.stringify(c.goldActionAlternates)
          : null,
      },
    });
  }

  for (const t of orderTemplates.templates) {
    await prisma.orderTemplate.upsert({
      where: { id: t.id },
      update: { orderJson: JSON.stringify(t.order) },
      create: { id: t.id, orderJson: JSON.stringify(t.order) },
    });
  }

  console.log("[seed] done");
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
