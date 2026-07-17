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
import { api, ApiError } from "@/lib/api/client";
import type { PostSurveyResponse } from "@/lib/api/types";
import { postSurveyConfig } from "@/lib/forms/postSurveyConfig";
import { zh } from "@/lib/i18n/zh-CN";
import { useStudy } from "@/lib/store";
import { PageBack } from "@/components/PageBack";
import { saveDraft, loadDraft, clearDraft } from "@/lib/persist";

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

  const draftKey = session ? `post:${session.sessionId}` : null;

  useEffect(() => {
    if (!session) router.replace("/consent");
  }, [session, router]);

  // Restore in-progress answers after a mobile WebView reload.
  useEffect(() => {
    if (!draftKey) return;
    const saved = loadDraft<Record<string, Answer>>(draftKey);
    if (saved) setAnswers(saved);
  }, [draftKey]);

  useEffect(() => {
    if (draftKey && Object.keys(answers).length > 0) saveDraft(draftKey, answers);
  }, [draftKey, answers]);

  const isItemAnswered = (it: { id: string; type?: string }): boolean => {
    const v = answers[it.id];
    if (it.type === "text") return typeof v === "string" && v.trim().length > 0;
    if (it.type === "phone4") return typeof v === "string" && /^\d{4}$/.test(v);
    return typeof v === "number"; // likert
  };

  const allAnswered = useMemo(() => {
    return postSurveyConfig.blocks
      .flatMap((b) => b.items)
      .every((it) => isItemAnswered(it));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answers]);

  /** First unanswered required item, in page order — for scroll-to + hint. */
  function firstMissing(): { id: string; count: number } | null {
    const items = postSurveyConfig.blocks.flatMap((b) => b.items);
    const missing = items.filter((it) => !isItemAnswered(it));
    if (missing.length === 0) return null;
    return { id: missing[0].id, count: missing.length };
  }

  async function submit() {
    if (!session) return;
    // Instead of a silently-disabled button, tell the participant exactly
    // what is left and jump them to it (they may have missed the attention
    // check or the phone field near the end).
    const miss = firstMissing();
    if (miss) {
      setError(`还有 ${miss.count} 道必答题未完成，已为您跳转到第一道未完成的题目。`);
      const el = document.getElementById(`q-${miss.id}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api<PostSurveyResponse>("/api/post-survey", {
        method: "POST",
        body: { sessionId: session.sessionId, payload: answers },
      });
      if (draftKey) clearDraft(draftKey);
      setCompletionCode(r.completionCode);
      setPerformance(r.performance ?? null);
      setStep("completion");
      router.push("/completion");
    } catch (e) {
      // A 422 means the payload failed backend validation (e.g. the
      // attention-check question was not answered with 4). Retrying the
      // same answers will fail identically, so tell the participant to
      // re-check their answers instead of showing a "retry later" network
      // message that would strand them in a loop.
      if (e instanceof ApiError && e.status === 422) {
        setError(zh.postSurvey.validationFailed);
      } else {
        setError(zh.errors.network);
      }
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
                <div key={it.id} id={`q-${it.id}`}>
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
                <div key={it.id} id={`q-${it.id}`}>
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
                <div key={it.id} id={`q-${it.id}`}>
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

      <div className="mt-7 flex flex-col items-end gap-2">
        {!allAnswered && (
          <p className="text-xs text-muted-foreground">
            带 <span className="text-destructive">*</span> 的题目均为必答；提交前请确认全部完成。
          </p>
        )}
        <button
          className="btn-primary"
          // Intentionally NOT disabled on incomplete answers: clicking runs
          // validation and jumps to the first missing item, instead of a
          // silently-greyed button that leaves the participant stuck.
          disabled={busy}
          onClick={submit}
        >
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {busy ? zh.postSurvey.saving : zh.postSurvey.submit}
        </button>
      </div>
    </div>
  );
}
