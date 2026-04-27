"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useStudyStore } from "@/lib/session-store";

export default function ConsentPage() {
  const router = useRouter();
  const setSession = useStudyStore((s) => s.setSession);
  const setStep = useStudyStore((s) => s.setStep);
  const reset = useStudyStore((s) => s.reset);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onContinue() {
    setBusy(true);
    setError(null);
    try {
      reset();
      const resp = await fetch("/api/session", { method: "POST" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      setSession(body);
      setStep("pre_survey");
      router.push("/pre-survey");
    } catch (e) {
      setError((e as Error).message ?? "Failed to start session");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card space-y-4 p-8">
      <h2 className="text-2xl font-semibold">Consent</h2>
      <div className="space-y-3 text-sm leading-6 text-slate-700">
        <p>
          You will review fictional patient messages and AI-drafted replies, and
          decide for each one how to handle it. There are no real patients
          involved.
        </p>
        <p>
          We record your choices, edits, click events, and timing. Your
          responses are stored under a pseudonymous participant ID. No personal
          health information is collected.
        </p>
        <p>
          You may stop at any time by closing the page. If you complete the
          study, you will see a completion code at the end.
        </p>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1"
        />
        <span>
          I have read the above and consent to participate in this study.
        </span>
      </label>

      {error && (
        <p className="text-sm text-red-600">Could not start session: {error}</p>
      )}

      <div className="flex justify-end">
        <button
          className="btn-primary"
          disabled={!agreed || busy}
          onClick={onContinue}
        >
          {busy ? "Starting..." : "I agree — continue"}
        </button>
      </div>
    </div>
  );
}
