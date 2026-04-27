"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CasePage } from "@/components/case/CasePage";
import { logEvent } from "@/lib/logger";
import { useStudyStore } from "@/lib/session-store";
import type { CasePayload } from "@/lib/types";

export default function PracticePage() {
  const router = useRouter();
  const session = useStudyStore((s) => s.session);
  const setStep = useStudyStore((s) => s.setStep);
  const setCaseIndex = useStudyStore((s) => s.setCaseIndex);
  const [casePayload, setCasePayload] = useState<CasePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) {
      router.replace("/consent");
      return;
    }
    void fetch(
      `/api/case/${session.practiceCaseId}?sessionId=${session.sessionId}`,
    )
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => setCasePayload(j.case))
      .catch((e) => setError((e as Error).message));
  }, [session, router]);

  if (error) {
    return <div className="card p-6 text-red-600">Error: {error}</div>;
  }
  if (!session || !casePayload) {
    return <div className="card p-6 text-slate-500">Loading...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="card border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        <strong>Practice case</strong> — get familiar with the layout, the four
        actions, and the three quick questions. This case is not counted in the
        main analysis.
      </div>
      <CasePage
        casePayload={casePayload}
        condition={session.condition}
        progressLabel="Practice"
        onLogEvent={(t, p) => logEvent(session.sessionId, t, p)}
        onSubmit={async (result) => {
          await fetch("/api/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sessionId: session.sessionId,
              caseId: casePayload.id,
              orderIndex: -1,
              isPractice: true,
              ...result,
            }),
          });
          setCaseIndex(0);
          setStep("case");
          router.push("/case/0");
        }}
      />
    </div>
  );
}
