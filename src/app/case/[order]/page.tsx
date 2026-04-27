"use client";

import { useRouter, useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CasePage } from "@/components/case/CasePage";
import { logEvent } from "@/lib/logger";
import { useStudyStore } from "@/lib/session-store";
import type { CasePayload } from "@/lib/types";

export default function FormalCasePage() {
  const router = useRouter();
  const params = useParams<{ order: string }>();
  const session = useStudyStore((s) => s.session);
  const setStep = useStudyStore((s) => s.setStep);
  const setCaseIndex = useStudyStore((s) => s.setCaseIndex);

  const orderIndex = Number(params.order);
  const [casePayload, setCasePayload] = useState<CasePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) {
      router.replace("/consent");
      return;
    }
    if (
      Number.isNaN(orderIndex) ||
      orderIndex < 0 ||
      orderIndex >= session.caseOrder.length
    ) {
      router.replace("/post-survey");
      return;
    }
    setCasePayload(null);
    setCaseIndex(orderIndex);
    const caseId = session.caseOrder[orderIndex];
    void fetch(`/api/case/${caseId}?sessionId=${session.sessionId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => setCasePayload(j.case))
      .catch((e) => setError((e as Error).message));
  }, [session, orderIndex, router, setCaseIndex]);

  if (error) {
    return <div className="card p-6 text-red-600">Error: {error}</div>;
  }
  if (!session || !casePayload) {
    return <div className="card p-6 text-slate-500">Loading...</div>;
  }

  const total = session.caseOrder.length;
  const progressLabel = `Case ${orderIndex + 1} / ${total}`;

  return (
    <CasePage
      casePayload={casePayload}
      condition={session.condition}
      progressLabel={progressLabel}
      onLogEvent={(t, p) => logEvent(session.sessionId, t, p)}
      onSubmit={async (result) => {
        await fetch("/api/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sessionId: session.sessionId,
            caseId: casePayload.id,
            orderIndex,
            isPractice: false,
            ...result,
          }),
        });

        const next = orderIndex + 1;
        if (next >= total) {
          setStep("post_survey");
          router.push("/post-survey");
        } else {
          setCaseIndex(next);
          router.push(`/case/${next}`);
        }
      }}
    />
  );
}
