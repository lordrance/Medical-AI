"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Edit3,
  RefreshCcw,
  Send,
  Loader2,
  FileText,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Likert } from "@/components/Likert";
import { VoiceInputButton } from "@/components/VoiceInputButton";
import { ProgressBar } from "@/components/ProgressBar";
import { cn } from "@/lib/cn";
import { zh } from "@/lib/i18n/zh-CN";
import type {
  ActionReasonCode,
  CasePayload,
  ClientStats,
  InteractionMetrics,
  CaseEmbeddedSurvey,
  SelectedAction,
} from "@/lib/api/types";

const ACTION_ORDER: SelectedAction[] = [
  "send_as_is",
  "edit_then_send",
  "discard_and_rewrite",
  "escalate",
];

// V4: send_as_is gets one extra reason "nothing_to_change" (PDF: 「基本
// 无误，可直接发送」). Other actions keep the V3 5-option set unchanged.
// We render the reasons by mapping over the per-action ordered list below.
const ACTION_REASON_ORDER_DEFAULT: ActionReasonCode[] = [
  "safety_risk",
  "insufficient_info",
  "wording_issue",
  "basically_ok",
  "other",
];
const ACTION_REASON_ORDER_SEND_AS_IS: ActionReasonCode[] = [
  "nothing_to_change",
  "safety_risk",
  "wording_issue",
  "other",
];

function reasonsForAction(action: SelectedAction | null): ActionReasonCode[] {
  if (action === "send_as_is") return ACTION_REASON_ORDER_SEND_AS_IS;
  return ACTION_REASON_ORDER_DEFAULT;
}

const ACTION_ICON: Record<SelectedAction, React.ComponentType<{ className?: string }>> = {
  send_as_is: Send,
  edit_then_send: Edit3,
  discard_and_rewrite: RefreshCcw,
  escalate: AlertTriangle,
};

const QUICK_ITEMS = [
  { id: "case_decision_confidence", text: "我对自己刚才作出的判断有信心。" },
  { id: "case_draft_helpfulness", text: "AI 起草的内容在本案例中是有帮助的。" },
];

export interface CasePageProps {
  casePayload: CasePayload;
  progressCurrent: number;
  progressTotal: number;
  practiceBanner?: boolean;
  /** 用于把 UI 事件写入 ui_events.case_presentation_id */
  casePresentationId?: string | null;
  onLogEvent?: (eventType: string, payload?: Record<string, unknown>) => void;
  onSubmit: (result: {
    selectedAction: SelectedAction;
    finalReplyText: string;
    escalateSubtype?: string;
    escalateReason?: string;
    caseActionReasonCode: ActionReasonCode;
    caseActionReasonText?: string;
    quickSurvey: CaseEmbeddedSurvey;
    timing: { startedAt: number; endedAt: number; durationMs: number };
    clientStats: ClientStats;
  }) => Promise<void>;
}

export function CasePage(props: CasePageProps) {
  const {
    casePayload,
    progressCurrent,
    progressTotal,
    practiceBanner,
    casePresentationId,
    onLogEvent,
    onSubmit,
  } = props;

  const chartExpandCountRef = useRef(0);
  const draftSourceSwitchCountRef = useRef(0);
  const chartEverViewedRef = useRef(false);
  const lastSectionRef = useRef<"chart" | "draft" | null>(null);
  const startedAtRef = useRef<number>(Date.now());
  const firstClickRef = useRef<number | null>(null);
  const panelClicksRef = useRef<Record<string, number>>({});
  const editKeystrokesRef = useRef(0);
  const editBoxOpenedRef = useRef(0);
  const checklistRef = useRef<boolean[]>([]);
  const checklistToggleRef = useRef(0); // checklist UI removed; kept for API shape
  const blurRef = useRef(0);
  const focusRef = useRef(0);
  const hiddenStartRef = useRef<number | null>(null);
  const visibilityHiddenRef = useRef(0);
  const draftScrollRef = useRef<HTMLDivElement | null>(null);
  const draftScrollEventsRef = useRef(0);
  const draftMaxScrollRatioRef = useRef(0);
  const draftFocusStartedAtRef = useRef<number | null>(null);
  const draftDwellMsRef = useRef(0);

  const [selected, setSelected] = useState<SelectedAction | null>(null);
  const [editorText, setEditorText] = useState("");
  const [escalateSubtype, setEscalateSubtype] = useState("");
  const [escalateReason, setEscalateReason] = useState("");
  const [actionReasonCode, setActionReasonCode] = useState<ActionReasonCode | "">("");
  const [actionReasonText, setActionReasonText] = useState("");
  const [showQuick, setShowQuick] = useState(false);
  const [quick, setQuick] = useState<Record<string, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [validationMsg, setValidationMsg] = useState<string | null>(null);
  const [chartExpanded, setChartExpanded] = useState(false);
  const [sendAsIsAck, setSendAsIsAck] = useState(false);

  function noteSectionFocus(section: "chart" | "draft") {
    const prev = lastSectionRef.current;
    // V4: only chart vs. draft remains (guardrail panel removed). A switch
    // between the two source contexts still counts toward
    // draft_source_context_switch for behavioural analysis continuity.
    if (prev !== null && prev !== section) {
      draftSourceSwitchCountRef.current += 1;
      onLogEvent?.("draft_source_context_switch", {
        caseId: casePayload.id,
        count: draftSourceSwitchCountRef.current,
      });
    }
    lastSectionRef.current = section;
  }

  function toggleChartExpand() {
    setChartExpanded((was) => {
      const next = !was;
      if (next && !was) {
        chartExpandCountRef.current += 1;
        chartEverViewedRef.current = true;
        onLogEvent?.("chart_expanded", { caseId: casePayload.id });
      }
      return next;
    });
  }
  // reset on case change
  useEffect(() => {
    startedAtRef.current = Date.now();
    firstClickRef.current = null;
    panelClicksRef.current = {};
    editKeystrokesRef.current = 0;
    editBoxOpenedRef.current = 0;
    checklistRef.current = [];
    checklistToggleRef.current = 0;
    blurRef.current = 0;
    focusRef.current = 0;
    hiddenStartRef.current = null;
    visibilityHiddenRef.current = 0;
    setSelected(null);
    setEditorText("");
    setEscalateSubtype("");
    setEscalateReason("");
    setActionReasonCode("");
    setActionReasonText("");
    setShowQuick(false);
    setQuick({});
    setValidationMsg(null);
    chartExpandCountRef.current = 0;
    draftSourceSwitchCountRef.current = 0;
    chartEverViewedRef.current = false;
    lastSectionRef.current = null;
    setChartExpanded(false);
    setSendAsIsAck(false);
    draftScrollEventsRef.current = 0;
    draftMaxScrollRatioRef.current = 0;
    draftFocusStartedAtRef.current = null;
    draftDwellMsRef.current = 0;
    onLogEvent?.("case_view_start", { caseId: casePayload.id });
  }, [casePayload.id]);

  // page blur / focus
  useEffect(() => {
    function vis() {
      if (document.visibilityState === "hidden") {
        blurRef.current += 1;
        hiddenStartRef.current = Date.now();
        onLogEvent?.("page_blur", { caseId: casePayload.id });
      } else {
        focusRef.current += 1;
        if (hiddenStartRef.current != null) {
          visibilityHiddenRef.current += Date.now() - hiddenStartRef.current;
          hiddenStartRef.current = null;
        }
        onLogEvent?.("page_focus", { caseId: casePayload.id });
      }
    }
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, [casePayload.id]);

  function recordFirstClick() {
    if (firstClickRef.current == null) firstClickRef.current = Date.now();
  }
  function bumpPanel(p: string) {
    panelClicksRef.current[p] = (panelClicksRef.current[p] ?? 0) + 1;
  }

  function chooseAction(a: SelectedAction) {
    recordFirstClick();
    bumpPanel("action_panel");
    setSelected(a);
    setValidationMsg(null);
    if (a !== "send_as_is") setSendAsIsAck(false);
    onLogEvent?.("action_button_selected", { caseId: casePayload.id, action: a });
    if (a === "edit_then_send") setEditorText(casePayload.aiDraft);
    else if (a === "discard_and_rewrite") setEditorText("");
    else if (a === "send_as_is") setEditorText(casePayload.aiDraft);
    else if (a === "escalate") {
      setEditorText("");
      setEscalateReason("");
    }
  }

  const editorVisible =
    selected === "edit_then_send" || selected === "discard_and_rewrite";

  const canContinue = useMemo(() => {
    if (!selected) return false;
    if (editorVisible && editorText.trim().length === 0) return false;
    if (selected === "escalate" && escalateReason.trim().length === 0) return false;
    if (selected === "send_as_is" && !sendAsIsAck) return false;
    return true;
  }, [selected, editorVisible, editorText, escalateReason, sendAsIsAck]);

  function tryContinue() {
    if (!selected) {
      setValidationMsg(zh.caseUI.pickAction);
      return;
    }
    if (editorVisible && editorText.trim().length === 0) {
      setValidationMsg(zh.caseUI.fillReply);
      return;
    }
    if (selected === "escalate" && escalateReason.trim().length === 0) {
      setValidationMsg(zh.escalateReason.required);
      return;
    }
    if (selected === "send_as_is" && !sendAsIsAck) {
      setValidationMsg(zh.caseUI.sendAsIsAckRequired);
      return;
    }
    onLogEvent?.("save_continue_clicked", { caseId: casePayload.id });
    setShowQuick(true);
  }

  const allQuickAnswered = useMemo(() => {
    const likertOk = QUICK_ITEMS.every((q) => typeof quick[q.id] === "number");
    if (!actionReasonCode) return false;
    if (actionReasonCode === "other" && !actionReasonText.trim()) return false;
    return likertOk;
  }, [quick, actionReasonCode, actionReasonText]);

  async function submitCase() {
    if (!allQuickAnswered || !selected) return;
    setSubmitting(true);
    const endedAt = Date.now();
    const durationMs = endedAt - startedAtRef.current;
    const finalReplyText =
      selected === "send_as_is"
        ? casePayload.aiDraft
        : selected === "escalate"
          ? "[escalated]"
          : editorText;
    const interactionMetrics: InteractionMetrics = {
      chartExpandToggleCount: chartExpandCountRef.current,
      // V4: guardrail panel removed; placeholder values kept so the backend
      // InteractionMetrics schema stays stable across V3/V4 data sets.
      guardrailExpandToggleCount: 0,
      draftSourceSwitchCount: draftSourceSwitchCountRef.current,
      chartEverExpandedToView: chartEverViewedRef.current,
      guardrailEverExpandedToView: false,
      sendAsIsAcknowledged: selected === "send_as_is" ? sendAsIsAck : false,
    };
    const clientStats: ClientStats = {
      timeToFirstClickMs:
        firstClickRef.current != null
          ? firstClickRef.current - startedAtRef.current
          : null,
      panelClickCounts: { ...panelClicksRef.current },
      checklistChecked: [...checklistRef.current],
      checklistToggleCount: checklistToggleRef.current,
      editKeystrokes: editKeystrokesRef.current,
      editBoxOpenedCount: editBoxOpenedRef.current,
      pageBlurCount: blurRef.current,
      pageFocusCount: focusRef.current,
      visibilityHiddenMs: visibilityHiddenRef.current,
      interactionMetrics,
      draftScrollEventCount: draftScrollEventsRef.current,
      draftScrollMaxDepthRatio: Number(draftMaxScrollRatioRef.current.toFixed(4)),
      draftSectionDwellMs: draftDwellMsRef.current,
    };
    try {
      await onSubmit({
        selectedAction: selected,
        finalReplyText,
        escalateSubtype:
          selected === "escalate" ? escalateSubtype || undefined : undefined,
        escalateReason:
          selected === "escalate" ? escalateReason.trim() : undefined,
        caseActionReasonCode: actionReasonCode as ActionReasonCode,
        caseActionReasonText:
          actionReasonCode === "other" ? actionReasonText.trim() : undefined,
        quickSurvey: {
          caseDecisionConfidence: quick["case_decision_confidence"]!,
          caseDraftHelpfulness: quick["case_draft_helpfulness"]!,
        },
        timing: { startedAt: startedAtRef.current, endedAt, durationMs },
        clientStats,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      {practiceBanner && (
        <div className="card card-section border-accent/40 bg-accent/5 text-sm text-foreground/80">
          {zh.practice.banner}
        </div>
      )}

      <ProgressBar
        current={progressCurrent}
        total={progressTotal}
        label={
          casePayload.isPractice
            ? zh.caseUI.practice
            : zh.caseUI.progress(progressCurrent, progressTotal)
        }
      />
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="font-mono text-foreground/90">
          {zh.caseUI.caseIdLabel}: {casePayload.id}
        </span>
        <span>
          {casePayload.isPractice
            ? zh.caseUI.practiceProgressHint
            : zh.caseUI.formalProgressHint(progressCurrent, progressTotal)}
        </span>
      </div>
      {!showQuick && (
        <>
          <Section
            title={zh.caseUI.patientMessage}
            icon={<FileText className="h-4 w-4" />}
            onClick={() => {
              recordFirstClick();
              bumpPanel("patient_message_panel");
              onLogEvent?.("panel_clicked", { panel: "patient_message_panel" });
            }}
          >
            <p className="whitespace-pre-line leading-relaxed">
              {casePayload.patientMessage}
            </p>
          </Section>

          <section className="card card-section">
            <button
              type="button"
              className="mb-3 flex w-full items-center justify-between gap-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
              onClick={() => {
                recordFirstClick();
                bumpPanel("chart_panel");
                onLogEvent?.("panel_clicked", { panel: "chart_panel" });
                toggleChartExpand();
              }}
            >
              <span>{zh.caseUI.chartSnapshot}</span>
              {chartExpanded ? (
                <ChevronUp className="h-4 w-4 shrink-0" />
              ) : (
                <ChevronDown className="h-4 w-4 shrink-0" />
              )}
            </button>
            {chartExpanded && (
              <div
                tabIndex={0}
                role="region"
                aria-label={zh.caseUI.chartSnapshot}
                onFocus={() => noteSectionFocus("chart")}
              >
                <ChartSnapshot snapshot={casePayload.chartSnapshot} />
              </div>
            )}
          </section>

          <Section
            title={zh.caseUI.aiDraft}
            onClick={() => {
              recordFirstClick();
              bumpPanel("ai_draft_panel");
              onLogEvent?.("panel_clicked", { panel: "ai_draft_panel" });
            }}
          >
            <div
              tabIndex={0}
              role="region"
              aria-label={zh.caseUI.aiDraft}
              onFocus={() => {
                noteSectionFocus("draft");
                if (draftFocusStartedAtRef.current == null) {
                  draftFocusStartedAtRef.current = Date.now();
                }
              }}
              onBlur={() => {
                if (draftFocusStartedAtRef.current != null) {
                  draftDwellMsRef.current += Date.now() - draftFocusStartedAtRef.current;
                  draftFocusStartedAtRef.current = null;
                }
              }}
            >
              <div
                ref={draftScrollRef}
                className="max-h-72 overflow-y-auto pr-1"
                onScroll={() => {
                  const el = draftScrollRef.current;
                  if (!el) return;
                  draftScrollEventsRef.current += 1;
                  const maxScroll = el.scrollHeight - el.clientHeight;
                  if (maxScroll > 0) {
                    const ratio = el.scrollTop / maxScroll;
                    draftMaxScrollRatioRef.current = Math.max(
                      draftMaxScrollRatioRef.current,
                      ratio,
                    );
                  }
                }}
              >
                <p className="whitespace-pre-line leading-relaxed">
                  {casePayload.aiDraft}
                </p>
              </div>
            </div>
            {selected === "send_as_is" && (
              <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-foreground/90">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 shrink-0 rounded border-border"
                  checked={sendAsIsAck}
                  onChange={(e) => {
                    recordFirstClick();
                    setSendAsIsAck(e.target.checked);
                    if (e.target.checked) {
                      onLogEvent?.("send_as_is_ack_checked", {
                        caseId: casePayload.id,
                      });
                    }
                  }}
                />
                <span>{zh.caseUI.sendAsIsAckLabel}</span>
              </label>
            )}
          </Section>

          <Section
            title={zh.caseUI.actionsHeading}
            onClick={() => bumpPanel("action_panel")}
          >
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {ACTION_ORDER.map((a) => {
                const Icon = ACTION_ICON[a];
                const active = selected === a;
                return (
                  <label
                    key={a}
                    className={cn("action-tile", active && "action-tile-active")}
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      checked={active}
                      onChange={() => chooseAction(a)}
                    />
                    <span className="action-tile-icon">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="space-y-0.5">
                      <span className="block font-semibold">
                        {zh.actions[a].label}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {zh.actions[a].hint}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>

            {selected === "escalate" && (
              <div className="mt-4 space-y-4">
                <div>
                  <label className="label">{zh.escalateSubtype.label}</label>
                  <select
                    className="input"
                    value={escalateSubtype}
                    onChange={(e) => setEscalateSubtype(e.target.value)}
                  >
                    {(
                      Object.entries(zh.escalateSubtype.options) as [
                        keyof typeof zh.escalateSubtype.options,
                        string,
                      ][]
                    ).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <label className="label flex-1">{zh.escalateReason.label}</label>
                    <VoiceInputButton
                      className="shrink-0"
                      value={escalateReason}
                      onChange={(next) => {
                        setEscalateReason(next);
                      }}
                      onVoiceActivity={(kind, detail) => {
                        onLogEvent?.(
                          kind === "started"
                            ? "voice_input_started"
                            : kind === "error"
                              ? "voice_input_error"
                              : "voice_input_ended",
                          {
                            caseId: casePayload.id,
                            field: "escalate_reason",
                            ...(detail?.code ? { code: detail.code } : {}),
                          },
                        );
                      }}
                    />
                  </div>
                  <textarea
                    className="textarea min-h-[100px]"
                    placeholder={zh.escalateReason.placeholder}
                    value={escalateReason}
                    onFocus={() => {
                      editBoxOpenedRef.current += 1;
                      onLogEvent?.("edit_box_opened", { caseId: casePayload.id });
                    }}
                    onChange={(e) => {
                      editKeystrokesRef.current += 1;
                      setEscalateReason(e.target.value);
                    }}
                  />
                </div>
              </div>
            )}

            {editorVisible && (
              <div className="mt-4">
                <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <label className="label flex-1">
                    {zh.caseUI.finalReplyLabel}
                    <span className="ml-2 font-normal text-muted-foreground">
                      {selected === "edit_then_send"
                        ? zh.caseUI.finalReplyHelpEdit
                        : zh.caseUI.finalReplyHelpRewrite}
                    </span>
                  </label>
                  <VoiceInputButton
                    className="shrink-0"
                    value={editorText}
                    onChange={setEditorText}
                    onVoiceActivity={(kind, detail) => {
                      onLogEvent?.(
                        kind === "started"
                          ? "voice_input_started"
                          : kind === "error"
                            ? "voice_input_error"
                            : "voice_input_ended",
                        {
                          caseId: casePayload.id,
                          field: "final_reply",
                          ...(detail?.code ? { code: detail.code } : {}),
                        },
                      );
                    }}
                  />
                </div>
                <textarea
                  className="textarea"
                  value={editorText}
                  onFocus={() => {
                    editBoxOpenedRef.current += 1;
                    onLogEvent?.("edit_box_opened", { caseId: casePayload.id });
                  }}
                  onChange={(e) => {
                    editKeystrokesRef.current += 1;
                    setEditorText(e.target.value);
                  }}
                />
                <div className="mt-1 text-right text-xs text-muted-foreground">
                  {zh.caseUI.chars(editorText.length)}
                </div>
              </div>
            )}
          </Section>

          {validationMsg && (
            <p className="text-sm text-destructive">{validationMsg}</p>
          )}

          <div className="flex justify-end">
            <button
              className="btn-primary"
              disabled={!canContinue}
              onClick={tryContinue}
            >
              {zh.caseUI.saveAndContinue}
            </button>
          </div>
        </>
      )}

      {showQuick && (
        <div className="card card-section animate-slide-up">
          <h3 className="text-lg font-semibold">{zh.caseUI.quickHeading}</h3>
          <div className="mt-4 space-y-3">
            <p className="text-sm font-medium text-foreground/90">
              {zh.caseUI.actionReasonHeading}
            </p>
            <div className="grid gap-2">
              {reasonsForAction(selected).map((code) => (
                <label
                  key={code}
                  className="flex cursor-pointer items-start gap-2 rounded-md border border-border/60 px-3 py-2 text-sm hover:bg-muted/40"
                >
                  <input
                    type="radio"
                    name="action_reason"
                    className="mt-1"
                    checked={actionReasonCode === code}
                    onChange={() => setActionReasonCode(code)}
                  />
                  <span>{zh.actionReason[code]}</span>
                </label>
              ))}
            </div>
            {actionReasonCode === "other" && (
              <div>
                <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <label className="label flex-1 text-sm font-medium">
                    {zh.caseUI.actionReasonOtherHeading}
                  </label>
                  <VoiceInputButton
                    className="shrink-0"
                    value={actionReasonText}
                    onChange={setActionReasonText}
                    disabled={submitting}
                    onVoiceActivity={(kind, detail) => {
                      onLogEvent?.(
                        kind === "started"
                          ? "voice_input_started"
                          : kind === "error"
                            ? "voice_input_error"
                            : "voice_input_ended",
                        {
                          caseId: casePayload.id,
                          field: "action_reason_other",
                          ...(detail?.code ? { code: detail.code } : {}),
                        },
                      );
                    }}
                  />
                </div>
                <textarea
                  className="textarea min-h-[72px]"
                  placeholder={zh.caseUI.actionReasonOtherPlaceholder}
                  value={actionReasonText}
                  onChange={(e) => setActionReasonText(e.target.value)}
                />
              </div>
            )}
          </div>
          <div className="mt-7 space-y-5">
            {QUICK_ITEMS.map((q) => (
              <div key={q.id}>
                <p className="mb-2 text-sm">{q.text}</p>
                <Likert
                  scale={{
                    min: 1,
                    max: 5,
                    minLabel: zh.scale.minLabel,
                    maxLabel: zh.scale.maxLabel,
                  }}
                  value={quick[q.id]}
                  onChange={(v) => setQuick({ ...quick, [q.id]: v })}
                  name={q.id}
                />
              </div>
            ))}
          </div>
          <div className="mt-7 flex justify-end">
            <button
              className="btn-primary"
              disabled={!allQuickAnswered || submitting}
              onClick={submitCase}
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {submitting ? zh.caseUI.saving : zh.caseUI.quickContinue}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ----- Sub-components -----

function Section({
  title,
  icon,
  children,
  onClick,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <section className="card card-section" onClick={onClick}>
      <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function ChartSnapshot({ snapshot }: { snapshot: Record<string, unknown> }) {
  const entries = Object.entries(snapshot).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  return (
    <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-md border border-border bg-muted/40 px-3 py-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {k}
          </dt>
          <dd className="text-foreground">{String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

