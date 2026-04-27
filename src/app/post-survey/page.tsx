"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useStudyStore } from "@/lib/session-store";
import postSurveyData from "@data/post_survey.json";

interface LikertItem {
  id: string;
  text: string;
  type?: "likert" | "text";
}
interface Block {
  id: string;
  title: string;
  items: LikertItem[];
}
interface PostSurveyData {
  title: string;
  description: string;
  scale: { min: number; max: number; minLabel: string; maxLabel: string };
  blocks: Block[];
}
const data = postSurveyData as PostSurveyData;

export default function PostSurveyPage() {
  const router = useRouter();
  const session = useStudyStore((s) => s.session);
  const setStep = useStudyStore((s) => s.setStep);
  const [answers, setAnswers] = useState<Record<string, number | string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) router.replace("/consent");
  }, [session, router]);

  const requiredItems = data.blocks.flatMap((b) =>
    b.items.filter((i) => i.type !== "text"),
  );
  const allAnswered = useMemo(
    () => requiredItems.every((it) => typeof answers[it.id] === "number"),
    [answers, requiredItems],
  );

  async function onSubmit() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/post-survey", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: session.sessionId,
          payload: answers,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setStep("completion");
      router.push("/completion");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card space-y-8 p-8">
      <header>
        <h2 className="text-2xl font-semibold">{data.title}</h2>
        <p className="mt-1 text-sm text-slate-600">{data.description}</p>
      </header>

      {data.blocks.map((block) => (
        <div key={block.id} className="space-y-4">
          <h3 className="border-b border-slate-200 pb-1 text-base font-semibold text-slate-800">
            {block.title}
          </h3>
          {block.items.map((it) =>
            it.type === "text" ? (
              <div key={it.id}>
                <label className="label">{it.text}</label>
                <textarea
                  className="textarea"
                  value={(answers[it.id] as string) ?? ""}
                  onChange={(e) =>
                    setAnswers({ ...answers, [it.id]: e.target.value })
                  }
                />
              </div>
            ) : (
              <div key={it.id}>
                <p className="mb-2 text-sm text-slate-800">{it.text}</p>
                <Likert
                  scale={data.scale}
                  value={answers[it.id] as number | undefined}
                  onChange={(v) => setAnswers({ ...answers, [it.id]: v })}
                />
              </div>
            ),
          )}
        </div>
      ))}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end">
        <button
          className="btn-primary"
          disabled={!allAnswered || busy}
          onClick={onSubmit}
        >
          {busy ? "Saving..." : "Submit"}
        </button>
      </div>
    </div>
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
