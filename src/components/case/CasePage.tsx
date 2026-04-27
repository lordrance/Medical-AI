"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CasePayload,
  Condition,
  SelectedAction,
} from "@/lib/types";
import { ALL_ACTIONS, ACTION_LABEL } from "@/lib/types";
import caseQuickSurveyData from "@data/case_quick_survey.json";

interface QuickSurveyItem {
  id: string;
  text: string;
}
interface QuickSurveyConfig {
  scale: { min: number; max: number; minLabel: string; maxLabel: string };
  items: QuickSurveyItem[];
}
const quickSurvey = caseQuickSurveyData as QuickSurveyConfig;

export interface CasePageProps {
  casePayload: CasePayload;
  condition: Condition;
  progressLabel: string;
  onSubmit: (result: {
    selectedAction: SelectedAction;
    finalReplyText: string;
    escalateSubtype?: string;
    quickSurvey: { item1: number; item2: number; item3: number };
    timing: { startedAt: number; endedAt: number; durationMs: number };
  }) => Promise<void> | void;
  onLogEvent?: (eventType: string, payload?: Record<string, unknown>) => void;
}

export function CasePage({
  casePayload,
  condition,
  progressLabel,
  onSubmit,
  onLogEvent,
}: CasePageProps) {
  const startedAtRef = useRef<number>(Date.now());
  const [selectedAction, setSelectedAction] =
    useState<SelectedAction | null>(null);
  const [editorText, setEditorText] = useState<string>("");
  const [escalateSubtype, setEscalateSubtype] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [showQuickSurvey, setShowQuickSurvey] = useState(false);
  const [surveyAnswers, setSurveyAnswers] = useState<Record<string, number>>({});

  useEffect(() => {
    startedAtRef.current = Date.now();
    setSelectedAction(null);
    setEditorText("");
    setEscalateSubtype("");
    setShowQuickSurvey(false);
    setSurveyAnswers({});
    onLogEvent?.("case_view_start", { caseId: casePayload.id });
  }, [casePayload.id, onLogEvent]);

  function chooseAction(a: SelectedAction) {
    setSelectedAction(a);
    onLogEvent?.("action_button_selected", { caseId: casePayload.id, action: a });
    if (a === "edit_then_send") {
      setEditorText(casePayload.aiDraft);
    } else if (a === "discard_and_rewrite") {
      setEditorText("");
    } else if (a === "send_as_is") {
      setEditorText(casePayload.aiDraft);
    } else if (a === "escalate") {
      setEditorText("");
    }
  }

  const editorVisible =
    selectedAction === "edit_then_send" ||
    selectedAction === "discard_and_rewrite";

  const canContinue = useMemo(() => {
    if (!selectedAction) return false;
    if (editorVisible && editorText.trim().length === 0) return false;
    return true;
  }, [selectedAction, editorVisible, editorText]);

  function handleSaveAndContinue() {
    if (!canContinue) return;
    onLogEvent?.("save_continue_clicked", { caseId: casePayload.id });
    setShowQuickSurvey(true);
  }

  const allSurveyAnswered = quickSurvey.items.every(
    (it) => typeof surveyAnswers[it.id] === "number",
  );

  async function handleQuickSurveySubmit() {
    if (!allSurveyAnswered || !selectedAction) return;
    setSubmitting(true);
    const endedAt = Date.now();
    const durationMs = endedAt - startedAtRef.current;
    const finalReplyText =
      selectedAction === "send_as_is"
        ? casePayload.aiDraft
        : selectedAction === "escalate"
          ? "[escalated]"
          : editorText;
    try {
      await onSubmit({
        selectedAction,
        finalReplyText,
        escalateSubtype:
          selectedAction === "escalate" ? escalateSubtype || undefined : undefined,
        quickSurvey: {
          item1: surveyAnswers["safe_to_send"],
          item2: surveyAnswers["confidence_in_judgment"],
          item3: surveyAnswers["ai_draft_helpful"],
        },
        timing: { startedAt: startedAtRef.current, endedAt, durationMs },
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-slate-600">{progressLabel}</div>
        <div className="text-xs text-slate-400">
          Condition:{" "}
          <span className="rounded bg-slate-200 px-2 py-0.5 font-mono text-slate-700">
            {condition}
          </span>
        </div>
      </div>

      {!showQuickSurvey && (
        <>
          <Section title="Patient Message" eventKey="patient_message_panel" onLogEvent={onLogEvent}>
            <p className="whitespace-pre-line leading-relaxed text-slate-800">
              {casePayload.patientMessage}
            </p>
          </Section>

          <Section title="Chart Snapshot" eventKey="chart_panel" onLogEvent={onLogEvent}>
            <ChartSnapshotView snapshot={casePayload.chartSnapshot} />
          </Section>

          <Section title="AI Draft Reply" eventKey="ai_draft_panel" onLogEvent={onLogEvent}>
            <p className="whitespace-pre-line leading-relaxed text-slate-800">
              {casePayload.aiDraft}
            </p>
          </Section>

          {condition === "guardrail" && casePayload.guardrail && (
            <GuardrailPanel
              guardrail={casePayload.guardrail}
              caseId={casePayload.id}
              onLogEvent={onLogEvent}
            />
          )}

          <Section title="Action" eventKey="action_panel" onLogEvent={onLogEvent}>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {ALL_ACTIONS.map((a) => (
                <button
                  key={a}
                  className={`btn ${
                    selectedAction === a
                      ? "border-brand-500 bg-brand-500 text-white"
                      : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
                  }`}
                  onClick={() => chooseAction(a)}
                  type="button"
                >
                  {ACTION_LABEL[a]}
                </button>
              ))}
            </div>

            {selectedAction === "escalate" && (
              <div className="mt-3">
                <label className="label">Escalation type (optional)</label>
                <select
                  className="input"
                  value={escalateSubtype}
                  onChange={(e) => setEscalateSubtype(e.target.value)}
                >
                  <option value="">—</option>
                  <option value="urgent_evaluation">Urgent evaluation</option>
                  <option value="call_patient">Call patient directly</option>
                  <option value="ed_instruction">ED instruction</option>
                  <option value="other">Other</option>
                </select>
              </div>
            )}

            {editorVisible && (
              <div className="mt-3">
                <label className="label">
                  Final reply{" "}
                  <span className="text-slate-400">
                    ({selectedAction === "edit_then_send"
                      ? "pre-filled with AI draft"
                      : "rewrite from scratch"})
                  </span>
                </label>
                <textarea
                  className="textarea"
                  value={editorText}
                  onFocus={() =>
                    onLogEvent?.("edit_box_opened", { caseId: casePayload.id })
                  }
                  onChange={(e) => setEditorText(e.target.value)}
                />
              </div>
            )}
          </Section>

          <div className="flex justify-end">
            <button
              className="btn-primary"
              disabled={!canContinue}
              onClick={handleSaveAndContinue}
            >
              Save &amp; Continue
            </button>
          </div>
        </>
      )}

      {showQuickSurvey && (
        <div className="card space-y-5 p-6">
          <h3 className="text-lg font-semibold">Three quick questions</h3>
          {quickSurvey.items.map((it) => (
            <div key={it.id}>
              <p className="mb-2 text-sm font-medium text-slate-800">{it.text}</p>
              <Likert
                scale={quickSurvey.scale}
                value={surveyAnswers[it.id]}
                onChange={(v) => setSurveyAnswers({ ...surveyAnswers, [it.id]: v })}
              />
            </div>
          ))}
          <div className="flex justify-end">
            <button
              className="btn-primary"
              disabled={!allSurveyAnswered || submitting}
              onClick={handleQuickSurveySubmit}
            >
              {submitting ? "Saving..." : "Continue"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  eventKey,
  children,
  onLogEvent,
}: {
  title: string;
  eventKey: string;
  children: React.ReactNode;
  onLogEvent?: (t: string, p?: Record<string, unknown>) => void;
}) {
  return (
    <section
      className="card p-5"
      onClick={() => onLogEvent?.("panel_clicked", { panel: eventKey })}
    >
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      {children}
    </section>
  );
}

function ChartSnapshotView({ snapshot }: { snapshot: Record<string, unknown> }) {
  const entries = Object.entries(snapshot).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return (
    <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {humanizeKey(k)}
          </dt>
          <dd className="text-slate-800">{String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function humanizeKey(k: string) {
  return k.replace(/([A-Z])/g, " $1").replace(/^./, (s) => s.toUpperCase());
}

function GuardrailPanel({
  guardrail,
  caseId,
  onLogEvent,
}: {
  guardrail: NonNullable<CasePayload["guardrail"]>;
  caseId: string;
  onLogEvent?: (t: string, p?: Record<string, unknown>) => void;
}) {
  const [checked, setChecked] = useState<boolean[]>(
    guardrail.checklist.map(() => false),
  );

  return (
    <section className="card border-amber-300 bg-amber-50 p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-amber-700">
        Guardrail Panel
      </h3>

      <div
        className="mb-3"
        onClick={() => onLogEvent?.("panel_clicked", { panel: "facts_panel", caseId })}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Facts used by AI
        </p>
        <ul className="mt-1 list-disc pl-5 text-sm text-slate-800">
          {guardrail.factsUsed.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      </div>

      <div
        className="mb-3"
        onClick={() => onLogEvent?.("panel_clicked", { panel: "risk_panel", caseId })}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Risk cue
        </p>
        <p className="mt-1 text-sm text-slate-800">{guardrail.riskCue}</p>
      </div>

      <div onClick={() => onLogEvent?.("panel_clicked", { panel: "checklist_panel", caseId })}>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Verification checklist
        </p>
        <ul className="mt-1 space-y-1 text-sm text-slate-800">
          {guardrail.checklist.map((c, i) => (
            <li key={i}>
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={checked[i]}
                  onChange={(e) => {
                    const next = [...checked];
                    next[i] = e.target.checked;
                    setChecked(next);
                    onLogEvent?.("checklist_item_toggled", {
                      caseId,
                      index: i,
                      checked: e.target.checked,
                    });
                  }}
                />
                <span>{c}</span>
              </label>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Likert({
  scale,
  value,
  onChange,
}: {
  scale: { min: number; max: number; minLabel: string; maxLabel: string };
  value: number | undefined;
  onChange: (v: number) => void;
}) {
  const points = Array.from(
    { length: scale.max - scale.min + 1 },
    (_, i) => scale.min + i,
  );
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        {points.map((p) => (
          <label
            key={p}
            className={`flex flex-1 cursor-pointer flex-col items-center rounded border px-2 py-2 text-xs ${
              value === p
                ? "border-brand-500 bg-brand-50"
                : "border-slate-200 hover:bg-slate-50"
            }`}
          >
            <input
              type="radio"
              className="sr-only"
              checked={value === p}
              onChange={() => onChange(p)}
            />
            <span className="font-semibold">{p}</span>
          </label>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-slate-500">
        <span>{scale.minLabel}</span>
        <span>{scale.maxLabel}</span>
      </div>
    </div>
  );
}
