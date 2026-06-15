// Hand-written, kept in sync with backend Pydantic schemas.
// (Phase 7 will switch to openapi-typescript-generated types.)

export type Condition = "plain" | "guardrail";

export type SelectedAction =
  | "send_as_is"
  | "edit_then_send"
  | "discard_and_rewrite"
  | "escalate";

export interface SessionInfo {
  sessionId: string;
  participantId: string;
  condition: Condition;
  orderTemplateId: number;
  caseOrder: string[];
  practiceCaseId: string;
}

export interface GuardrailContent {
  factsUsed: string[];
  riskCue: string;
  checklist: string[];
}

export interface CasePayload {
  id: string;
  isPractice: boolean;
  riskLevel: string;
  patientMessage: string;
  chartSnapshot: Record<string, unknown>;
  aiDraft: string;
  guardrail?: GuardrailContent | null;
}

export interface CaseResponse {
  case: CasePayload;
}

export interface QuickSurvey {
  item1: number;
  item2: number;
  item3: number;
}

export interface ClientStats {
  timeToFirstClickMs: number | null;
  panelClickCounts: Record<string, number>;
  checklistChecked: boolean[];
  checklistToggleCount: number;
  editKeystrokes: number;
  editBoxOpenedCount: number;
  pageBlurCount: number;
  pageFocusCount: number;
  visibilityHiddenMs: number;
}

export interface ActionResponse {
  ok: boolean;
  casePresentationId: string;
  editDistance: number;
}

export interface SessionPerformance {
  correct: number;
  total: number;
  accuracy: number;
}

export interface PostSurveyResponse {
  ok: boolean;
  completionCode: string;
  performance?: SessionPerformance;
}

export interface ConfusionMatrix {
  actions: SelectedAction[];
  actionsZh: string[];
  matrix: number[][];
  total: number;
  accuracy: number;
}

export interface SummaryResponse {
  completion: {
    totalParticipants: number;
    completed: number;
    completionRate: number;
    byCondition: { condition: string; count: number }[];
  };
  confusionMatrix: ConfusionMatrix;
  perCase: {
    caseId: string;
    defectPresent: boolean;
    riskLevel: string;
    goldAction: string;
    goldActionZh: string;
    total: number;
    matchGold: number;
    matchAlternates: number;
    unsafeSendAsIs: number;
    errorSurvival: number;
    appropriateEscalation: number;
    meanDurationMs: number;
    meanEditDistance: number;
  }[];
  perParticipant: {
    participantId: string;
    condition: string;
    total: number;
    matchGold: number;
    accuracy: number;
    errorSurvivalCount: number;
    appropriateEscalationCount: number;
    meanDurationMs: number;
    meanEditDistance: number;
  }[];
}

export interface LlmSummaryResponse {
  summaryText: string;
  provider: string;
  model: string;
  promptTokens: number | null;
  completionTokens: number | null;
  latencyMs: number;
}

export interface DashboardHealthResponse {
  dbConnected: boolean;
  serverTime: string;
  llmErrors24h: number;
  activeSessions: number;
}
