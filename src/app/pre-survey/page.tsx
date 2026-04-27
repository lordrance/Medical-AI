"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useStudyStore } from "@/lib/session-store";
import preSurveyData from "@data/pre_survey.json";

interface PreSurveyItem {
  id: string;
  type: "select" | "number" | "likert";
  label: string;
  required?: boolean;
  options?: string[];
  min?: number;
  max?: number;
  scale?: { min: number; max: number; minLabel: string; maxLabel: string };
}

interface PreSurveyData {
  title: string;
  description: string;
  items: PreSurveyItem[];
}

const data = preSurveyData as PreSurveyData;

export default function PreSurveyPage() {
  const router = useRouter();
  const session = useStudyStore((s) => s.session);
  const setStep = useStudyStore((s) => s.setStep);
  const [answers, setAnswers] = useState<Record<string, string | number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) router.replace("/consent");
  }, [session, router]);

  const allAnswered = useMemo(() => {
    return data.items.every((item) => {
      if (!item.required) return true;
      const v = answers[item.id];
      return v !== undefined && v !== "" && v !== null;
    });
  }, [answers]);

  async function onSubmit() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/pre-survey", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: session.sessionId,
          answers,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setStep("practice");
      router.push("/practice");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card space-y-6 p-8">
      <header>
        <h2 className="text-2xl font-semibold">{data.title}</h2>
        <p className="mt-1 text-sm text-slate-600">{data.description}</p>
      </header>

      <div className="space-y-5">
        {data.items.map((item) => (
          <div key={item.id}>
            <label className="label">
              {item.label}
              {item.required && <span className="ml-1 text-red-500">*</span>}
            </label>

            {item.type === "select" && (
              <select
                className="input"
                value={(answers[item.id] as string) ?? ""}
                onChange={(e) =>
                  setAnswers({ ...answers, [item.id]: e.target.value })
                }
              >
                <option value="">—</option>
                {item.options?.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            )}

            {item.type === "number" && (
              <input
                type="number"
                className="input"
                min={item.min}
                max={item.max}
                value={(answers[item.id] as number | undefined) ?? ""}
                onChange={(e) =>
                  setAnswers({
                    ...answers,
                    [item.id]:
                      e.target.value === "" ? "" : Number(e.target.value),
                  })
                }
              />
            )}

            {item.type === "likert" && item.scale && (
              <LikertScale
                scale={item.scale}
                value={answers[item.id] as number | undefined}
                onChange={(v) => setAnswers({ ...answers, [item.id]: v })}
              />
            )}
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end">
        <button
          className="btn-primary"
          disabled={!allAnswered || busy}
          onClick={onSubmit}
        >
          {busy ? "Saving..." : "Continue"}
        </button>
      </div>
    </div>
  );
}

function LikertScale({
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
              name={`likert-${scale.min}-${scale.max}`}
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
