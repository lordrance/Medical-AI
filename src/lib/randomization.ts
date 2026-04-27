import type { Condition } from "./types";

export function assignCondition(): Condition {
  return Math.random() < 0.5 ? "plain" : "guardrail";
}

export function pickOrderTemplateId(templateIds: number[]): number {
  if (templateIds.length === 0) {
    throw new Error("No order templates available");
  }
  const idx = Math.floor(Math.random() * templateIds.length);
  return templateIds[idx];
}
