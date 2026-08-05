"use client";

/**
 * 前测问卷 —— 答题前采集医生的基本信息（科室、职级、年资等）。
 *
 * 题目内容不在这个文件里，在 lib/forms/preSurveyConfig.ts。
 * 这里只负责「按配置渲染表单 + 收集答案 + 提交」，改题目去改那个配置文件。
 *
 * ★ 这里有防丢失机制：每改一个答案就存进 localStorage，
 *   手机刷新/切后台回来能自动恢复（见 lib/persist.ts）。
 */

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Likert } from "@/components/Likert";
import { api, isSessionInvalid } from "@/lib/api/client";
import { preSurveyConfig } from "@/lib/forms/preSurveyConfig";
import { zh } from "@/lib/i18n/zh-CN";
import { useStudy } from "@/lib/store";
import { PageBack } from "@/components/PageBack";
import { saveDraft, loadDraft, clearDraft } from "@/lib/persist";

type Answer = string | number | string[];

export default function PreSurveyPage() {
  const router = useRouter();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 草稿的存储键。带上 sessionId，不同人/不同次的草稿互不干扰。
  const draftKey = session ? `pre:${session.sessionId}` : null;

  // 守卫：没有会话就回到入口（直接输网址进来的情况）
  useEffect(() => {
    if (!session) router.replace("/consent");
  }, [session, router]);

  // Restore any in-progress answers after a mobile WebView reload.
  // 中文：页面加载时把上次没填完的答案读回来。
  useEffect(() => {
    if (!draftKey) return;
    const saved = loadDraft<Record<string, Answer>>(draftKey);
    if (saved) setAnswers(saved);
  }, [draftKey]);

  // Persist on every change so a reload never loses typed answers.
  // 中文：每改一个答案就立刻存一次。依赖项里有 answers，
  // 所以 answers 一变这个 effect 就重跑。
  useEffect(() => {
    if (draftKey && Object.keys(answers).length > 0) saveDraft(draftKey, answers);
  }, [draftKey, answers]);

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
      if (draftKey) clearDraft(draftKey);
      setStep("practice");
      router.push("/practice");
    } catch (e) {
      if (isSessionInvalid(e)) {
        useStudy.getState().reset();
        router.replace("/consent");
        return;
      }
      setError(zh.errors.network);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card card-section animate-slide-up">
      <PageBack hide />
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
