export type Condition = "plain" | "guardrail";

export type SelectedAction =
  | "send_as_is"
  | "edit_then_send"
  | "discard_and_rewrite"
  | "escalate";

export const ALL_ACTIONS: SelectedAction[] = [
  "send_as_is",
  "edit_then_send",
  "discard_and_rewrite",
  "escalate",
];

export const ACTION_LABEL: Record<SelectedAction, string> = {
  send_as_is: "Send as is",
  edit_then_send: "Edit then send",
  discard_and_rewrite: "Discard and rewrite",
  escalate: "Escalate",
};

export interface ChartSnapshot {
  age?: number;
  history?: string;
  medications?: string;
  allergies?: string;
  recentResults?: string;
  nextVisit?: string;
  [k: string]: unknown;
}

export interface CasePayload {
  id: string;
  isPractice: boolean;
  riskLevel: string;
  patientMessage: string;
  chartSnapshot: ChartSnapshot;
  aiDraft: string;
  guardrail?: {
    factsUsed: string[];
    riskCue: string;
    checklist: string[];
  };
}

export interface SessionInfo {
  sessionId: string;
  participantId: string;
  condition: Condition;
  orderTemplateId: number;
  caseOrder: string[];
  practiceCaseId: string;
}
