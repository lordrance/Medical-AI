"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Likert } from "@/components/Likert";
import { api } from "@/lib/api/client";
import type { PostSurveyResponse } from "@/lib/api/types";
import { postSurveyConfig } from "@/lib/forms/postSurveyConfig";
import { zh } from "@/lib/i18n/zh-CN";
import { useStudy } from "@/lib/store";
import { PageBack } from "@/components/PageBack";

type Answer = number | string;

export default function PostSurveyPage() {
  const router = useRouter();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const setCompletionCode = useStudy((s) => s.setCompletionCode);
  const setPerformance = useStudy((s) => s.setPerformance);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) router.replace("/consent");
  }, [session, router]);

  const requiredLikertItems = postSurveyConfig.blocks.flatMap((b) =>
    b.items.filter((i) => i.type !== "text"),
  );
  const requiredTextItems = postSurveyConfig.blocks.flatMap((b) =>
    b.items.filter((i) => i.type === "text"),
  );
  const allAnswered = useMemo(() => {
    const likertOk = requiredLikertItems.every(
      (it) => typeof answers[it.id] === "number",
    );
    const textOk = requiredTextItems.every((it) => {
      const v = answers[it.id];
      return typeof v === "string" && v.trim().length > 0;
    });
    return likertOk && textOk;
  }, [answers, requiredLikertItems, requiredTextItems]);

  async function submit() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<PostSurveyResponse>("/api/post-survey", {
        method: "POST",
        body: { sessionId: session.sessionId, payload: answers },
      });
      setCompletionCode(r.completionCode);
      setPerformance(r.performance ?? null);
      setStep("completion");
      router.push("/completion");
    } catch {
      setError(zh.errors.network);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card card-section animate-slide-up">
      <PageBack hide />
      <h2 className="text-xl font-semibold">{postSurveyConfig.title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {postSurveyConfig.description}
      </p>

      <div className="mt-7 space-y-8">
        {postSurveyConfig.blocks.map((b) => (
          <section key={b.id} className="space-y-4">
            <h3 className="border-b border-border pb-1 text-base font-semibold">
              {b.title}
            </h3>
            {b.items.map((it) =>
              it.type === "text" ? (
                <div key={it.id}>
                  <label className="label whitespace-pre-line">{it.text}</label>
                  <textarea
                    className="textarea mt-2 min-h-[140px]"
                    rows={6}
                    value={(answers[it.id] as string) ?? ""}
                    onChange={(e) =>
                      setAnswers({ ...answers, [it.id]: e.target.value })
                    }
                  />
                </div>
              ) : (
                <div key={it.id}>
                  <p className="mb-2 text-sm">{it.text}</p>
                  <Likert
                    scale={postSurveyConfig.scale}
                    value={answers[it.id] as number | undefined}
                    onChange={(v) =>
                      setAnswers({ ...answers, [it.id]: v })
                    }
                    name={it.id}
                  />
                </div>
              ),
            )}
          </section>
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
          {busy ? zh.postSurvey.saving : zh.postSurvey.submit}
        </button>
      </div>
    </div>
  );
}
