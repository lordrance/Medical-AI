"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { Likert } from "@/components/Likert";
// V4: Web Speech API speech-to-text disabled. Chrome's webkitSpeechRecognition
// uses Google's cloud STT service, which is unreachable in mainland China.
// Component source kept at frontend/src/components/VoiceInputButton.tsx for
// possible future restoration via a domestic STT backend.
// import { VoiceInputButton } from "@/components/VoiceInputButton";
import { VoiceRecorderButton } from "@/components/VoiceRecorderButton";
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
    b.items.filter((i) => i.type !== "text" && i.type !== "phone4"),
  );
  const requiredTextItems = postSurveyConfig.blocks.flatMap((b) =>
    b.items.filter((i) => i.type === "text"),
  );
  const requiredPhone4Items = postSurveyConfig.blocks.flatMap((b) =>
    b.items.filter((i) => i.type === "phone4"),
  );
  const allAnswered = useMemo(() => {
    const likertOk = requiredLikertItems.every(
      (it) => typeof answers[it.id] === "number",
    );
    const textOk = requiredTextItems.every((it) => {
      const v = answers[it.id];
      return typeof v === "string" && v.trim().length > 0;
    });
    const phone4Ok = requiredPhone4Items.every((it) => {
      const v = answers[it.id];
      return typeof v === "string" && /^\d{4}$/.test(v);
    });
    return likertOk && textOk && phone4Ok;
  }, [answers, requiredLikertItems, requiredTextItems, requiredPhone4Items]);

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
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <label className="label flex-1 whitespace-pre-line">{it.text}</label>
                    {/* V4: VoiceInputButton (Web Speech API → Google STT)
                        removed; mainland China cannot reach the Google
                        service. Restore by re-importing VoiceInputButton
                        in this file and the JSX below.
                    <VoiceInputButton
                      className="shrink-0"
                      value={(answers[it.id] as string) ?? ""}
                      onChange={(next) =>
                        setAnswers({ ...answers, [it.id]: next })
                      }
                      disabled={busy}
                    /> */}
                  </div>
                  <textarea
                    className="textarea mt-2 min-h-[140px]"
                    rows={6}
                    value={(answers[it.id] as string) ?? ""}
                    onChange={(e) =>
                      setAnswers({ ...answers, [it.id]: e.target.value })
                    }
                  />
                  {session && (
                    <div className="mt-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2">
                      <p className="mb-1 text-xs font-medium text-foreground/80">
                        语音补充（可选，将由研究团队事后人工转写）
                      </p>
                      <VoiceRecorderButton
                        sessionId={session.sessionId}
                        questionId={it.id}
                      />
                    </div>
                  )}
                </div>
              ) : it.type === "phone4" ? (
                <div key={it.id}>
                  <label className="label whitespace-pre-line">{it.text}</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={4}
                    className="input mt-2 w-40 tracking-widest"
                    placeholder="0000"
                    value={(answers[it.id] as string) ?? ""}
                    onChange={(e) => {
                      const digits = e.target.value.replace(/\D/g, "").slice(0, 4);
                      setAnswers({ ...answers, [it.id]: digits });
                    }}
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
