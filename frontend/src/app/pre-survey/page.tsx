"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Likert } from "@/components/Likert";
import { api } from "@/lib/api/client";
import { preSurveyConfig } from "@/lib/forms/preSurveyConfig";
import { zh } from "@/lib/i18n/zh-CN";
import { useStudy } from "@/lib/store";

type Answer = string | number | string[];

export default function PreSurveyPage() {
  const router = useRouter();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) router.replace("/consent");
  }, [session, router]);

  const allAnswered = useMemo(
    () =>
      preSurveyConfig.items.every((it) => {
        if (!it.required) return true;
        const v = answers[it.id];
        if (v === undefined || v === null) return false;
        if (typeof v === "string" && v.trim() === "") return false;
        return true;
      }),
    [answers],
  );

  async function submit() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await api("/api/pre-survey", {
        method: "POST",
        body: { sessionId: session.sessionId, answers },
      });
      setStep("practice");
      router.push("/practice");
    } catch (e) {
      setError(zh.errors.network);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card card-section animate-slide-up">
      <h2 className="text-xl font-semibold">{preSurveyConfig.title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {preSurveyConfig.description}
      </p>

      <div className="mt-7 space-y-6">
        {preSurveyConfig.items.map((item) => (
          <div key={item.id}>
            <label className="label">
              {item.label}
              {item.required && (
                <span className="ml-1 text-destructive">*</span>
              )}
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

            {item.type === "multi_select" && (
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {item.options?.map((opt) => {
                  const selected = ((answers[item.id] as string[]) ?? []).includes(
                    opt,
                  );
                  return (
                    <label
                      key={opt}
                      className={`flex cursor-pointer items-center gap-2 rounded border border-border bg-card px-3 py-2 text-sm transition hover:border-primary/40 ${
                        selected ? "border-primary bg-primary/5" : ""
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
                        checked={selected}
                        onChange={() => {
                          const cur = (answers[item.id] as string[]) ?? [];
                          setAnswers({
                            ...answers,
                            [item.id]: selected
                              ? cur.filter((x) => x !== opt)
                              : [...cur, opt],
                          });
                        }}
                      />
                      <span>{opt}</span>
                    </label>
                  );
                })}
              </div>
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
              <Likert
                scale={item.scale}
                value={answers[item.id] as number | undefined}
                onChange={(v) =>
                  setAnswers({ ...answers, [item.id]: v })
                }
                name={item.id}
              />
            )}
          </div>
        ))}
      </div>

      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

      <div className="mt-7 flex justify-end">
        <button
          className="btn-primary"
          disabled={!allAnswered || busy}
          onClick={submit}
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {busy ? zh.preSurvey.saving : zh.preSurvey.submit}
        </button>
      </div>
    </div>
  );
}
