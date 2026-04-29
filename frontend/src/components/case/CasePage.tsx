"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Edit3,
  RefreshCcw,
  Send,
  Loader2,
  AlertOctagon,
  FileText,
} from "lucide-react";
import { Likert } from "@/components/Likert";
import { ProgressBar } from "@/components/ProgressBar";
import { cn } from "@/lib/cn";
import { zh } from "@/lib/i18n/zh-CN";
import type {
  CasePayload,
  ClientStats,
  Condition,
  QuickSurvey,
  SelectedAction,
} from "@/lib/api/types";

const ACTION_ORDER: SelectedAction[] = [
  "send_as_is",
  "edit_then_send",
  "discard_and_rewrite",
  "escalate",
];

const ACTION_ICON: Record<SelectedAction, React.ComponentType<{ className?: string }>> = {
  send_as_is: Send,
  edit_then_send: Edit3,
  discard_and_rewrite: RefreshCcw,
  escalate: AlertTriangle,
};

const QUICK_ITEMS = [
  { id: "safe_to_send", text: "我认为这条最终回复现在可以安全地发送给患者。" },
  { id: "confidence_in_judgment", text: "我对自己刚才作出的判断有信心。" },
  { id: "ai_draft_helpful", text: "AI 起草的内容在本案例中是有帮助的。" },
];

export interface CasePageProps {
  casePayload: CasePayload;
  condition: Condition;
  progressCurrent: number;
  progressTotal: number;
  practiceBanner?: boolean;
  onLogEvent?: (eventType: string, payload?: Record<string, unknown>) => void;
  onSubmit: (result: {
    selectedAction: SelectedAction;
    finalReplyText: string;
    escalateSubtype?: string;
    escalateReason?: string;
    quickSurvey: QuickSurvey;
    timing: { startedAt: number; endedAt: number; durationMs: number };
    clientStats: ClientStats;
  }) => Promise<void>;
}

export function CasePage(props: CasePageProps) {
  const {
    casePayload,
    condition,
    progressCurrent,
    progressTotal,
    practiceBanner,
    onLogEvent,
    onSubmit,
  } = props;

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

  const [selected, setSelected] = useState<SelectedAction | null>(null);
  const [editorText, setEditorText] = useState("");
  const [escalateSubtype, setEscalateSubtype] = useState("");
  const [escalateReason, setEscalateReason] = useState("");
  const [showQuick, setShowQuick] = useState(false);
  const [quick, setQuick] = useState<Record<string, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [validationMsg, setValidationMsg] = useState<string | null>(null);

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
    setShowQuick(false);
    setQuick({});
    setValidationMsg(null);
    onLogEvent?.("case_view_start", { caseId: casePayload.id });
  }, [casePayload.id, casePayload.guardrail, onLogEvent]);

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
  }, [casePayload.id, onLogEvent]);

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
    return true;
  }, [selected, editorVisible, editorText, escalateReason]);

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
    onLogEvent?.("save_continue_clicked", { caseId: casePayload.id });
    setShowQuick(true);
  }

  const allQuickAnswered = QUICK_ITEMS.every((q) => typeof quick[q.id] === "number");

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
    };
    try {
      await onSubmit({
        selectedAction: selected,
        finalReplyText,
        escalateSubtype:
          selected === "escalate" ? escalateSubtype || undefined : undefined,
        escalateReason:
          selected === "escalate" ? escalateReason.trim() : undefined,
        quickSurvey: {
          item1: quick["safe_to_send"],
          item2: quick["confidence_in_judgment"],
          item3: quick["ai_draft_helpful"],
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
      <div className="text-xs text-muted-foreground">
        {zh.caseUI.condition(condition)}
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

          <Section
            title={zh.caseUI.chartSnapshot}
            onClick={() => {
              recordFirstClick();
              bumpPanel("chart_panel");
              onLogEvent?.("panel_clicked", { panel: "chart_panel" });
            }}
          >
            <ChartSnapshot snapshot={casePayload.chartSnapshot} />
          </Section>

          <Section
            title={zh.caseUI.aiDraft}
            onClick={() => {
              recordFirstClick();
              bumpPanel("ai_draft_panel");
              onLogEvent?.("panel_clicked", { panel: "ai_draft_panel" });
            }}
          >
            <p className="whitespace-pre-line leading-relaxed">
              {casePayload.aiDraft}
            </p>
          </Section>

          {condition === "guardrail" && casePayload.guardrail && (
            <GuardrailPanel
              guardrail={casePayload.guardrail}
              caseId={casePayload.id}
              onPanelClick={(p) => {
                recordFirstClick();
                bumpPanel(p);
              }}
              onLogEvent={onLogEvent}
            />
          )}

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
                  <label className="label">{zh.escalateReason.label}</label>
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
                <label className="label">
                  {zh.caseUI.finalReplyLabel}
                  <span className="ml-2 text-muted-foreground font-normal">
                    {selected === "edit_then_send"
                      ? zh.caseUI.finalReplyHelpEdit
                      : zh.caseUI.finalReplyHelpRewrite}
                  </span>
                </label>
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
          <div className="mt-5 space-y-5">
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

function GuardrailPanel({
  guardrail,
  caseId,
  onPanelClick,
  onLogEvent,
}: {
  guardrail: NonNullable<CasePayload["guardrail"]>;
  caseId: string;
  onPanelClick: (panel: string) => void;
  onLogEvent?: (t: string, p?: Record<string, unknown>) => void;
}) {
  return (
    <section className="guardrail-panel">
      <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-accent-foreground">
        <AlertOctagon className="h-4 w-4 text-accent" />
        {zh.caseUI.guardrailTitle}
      </h3>

      <div
        onClick={() => {
          onPanelClick("facts_panel");
          onLogEvent?.("panel_clicked", { panel: "facts_panel", caseId });
        }}
      >
        <p className="mb-1.5 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <FileText className="h-3.5 w-3.5" />
          {zh.caseUI.factsUsed}
        </p>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {guardrail.factsUsed.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      </div>

      <div
        onClick={() => {
          onPanelClick("risk_panel");
          onLogEvent?.("panel_clicked", { panel: "risk_panel", caseId });
        }}
      >
        <p className="mb-1.5 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5" />
          {zh.caseUI.riskCue}
        </p>
        <p className="rounded-md bg-card/80 px-3 py-2 text-sm">{guardrail.riskCue}</p>
      </div>
    </section>
  );
}
