// Hand-written, kept in sync with backend Pydantic schemas.
// (Phase 7 will switch to openapi-typescript-generated types.)

// V4: single-condition study; the V3 "plain" | "guardrail" union collapses
// to a single literal. Kept as a named type so SessionInfo / store / etc.
// don't have to drop the field entirely (the backend still stores it).
export type Condition = "single";

export type SelectedAction =
  | "send_as_is"
  | "edit_then_send"
  | "discard_and_rewrite"
  | "escalate";

export type ActionReasonCode =
  | "safety_risk"
  | "insufficient_info"
  | "wording_issue"
  | "basically_ok"
  | "nothing_to_change"
  | "other";

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

/** 案例末嵌入式量表（问卷 7.0，对应 `case_decision_confidence` / `case_draft_helpfulness`） */
export interface CaseEmbeddedSurvey {
  caseDecisionConfidence: number;
  caseDraftHelpfulness: number;
}

export interface InteractionMetrics {
  /** 病历摘要展开次数（从收起切到展开） */
  chartExpandToggleCount: number;
  /** 护栏区整体展开次数（仅 guardrail 组有意义） */
  guardrailExpandToggleCount: number;
  /** 草稿区与「源信息」（病历/护栏核查）之间的焦点切换次数 */
  draftSourceSwitchCount: number;
  /** 是否曾展开查看病历摘要 */
  chartEverExpandedToView: boolean;
  /** 是否曾展开查看护栏（AI 总结/风险提示） */
  guardrailEverExpandedToView: boolean;
  /** 选择「原样发送」前是否勾选核对确认 */
  sendAsIsAcknowledged: boolean;
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
  interactionMetrics?: InteractionMetrics;
  draftScrollEventCount?: number;
  draftScrollMaxDepthRatio?: number;
  draftSectionDwellMs?: number;
}

export interface ActionResponse {
  ok: boolean;
  casePresentationId: string;
  editDistance: number;
}

export interface CaseOpenResponse {
  casePresentationId: string;
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

// ---------------------------------------------------------------------------
// Research dashboard (Phase B) — mirrors backend/app/api/admin/dashboard.py
// ---------------------------------------------------------------------------

export interface LlmStatsResponse {
  totals: {
    count: number;
    errors: number;
    errorRate: number;
    promptTokens: number;
    completionTokens: number;
  };
  perPurpose: {
    purpose: string;
    count: number;
    errorRate: number;
    p50Ms: number;
    p95Ms: number;
    promptTokens: number;
    completionTokens: number;
    count24h: number;
  }[];
}

export interface CompletionTimeseriesPoint {
  ts: string; // ISO 8601, bucket-truncated
  started: number;
  completed: number;
}

export interface LogStatsOverallMetric {
  key: string;
  mean: number;
  n: number;
}

export interface LogStatsOverallResponse {
  metrics: LogStatsOverallMetric[];
}

export interface UiEventFrequencyRow {
  eventType: string;
  count: number;
  splits?: Record<string, number>;
}

export interface ActiveSessionRow {
  sessionId: string;
  participantId: string;
  condition: string | null;
  startedAt: string | null;
  elapsedMs: number;
  lastEventAt: string | null;
  lastEventType: string | null;
}

export interface DashboardOverviewResponse {
  llmStats: LlmStatsResponse;
  timeseries: CompletionTimeseriesPoint[];
  logOverall: LogStatsOverallResponse;
  uiEvents: UiEventFrequencyRow[];
  activeSessions: ActiveSessionRow[];
}
