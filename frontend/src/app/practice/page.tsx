"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CasePage } from "@/components/case/CasePage";
import { api } from "@/lib/api/client";
import type { ActionResponse, CaseResponse, CasePayload } from "@/lib/api/types";
import { logEvent } from "@/lib/logger";
import { useStudy } from "@/lib/store";
import { zh } from "@/lib/i18n/zh-CN";

export default function PracticePage() {
  const router = useRouter();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const setCaseIndex = useStudy((s) => s.setCaseIndex);
  const [casePayload, setCasePayload] = useState<CasePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) {
      router.replace("/consent");
      return;
    }
    void api<CaseResponse>(`/api/case/${session.practiceCaseId}`, {
      query: { sessionId: session.sessionId },
    })
      .then((r) => setCasePayload(r.case))
      .catch((e) => setError((e as Error).message));
  }, [session, router]);

  if (error) return <div className="card card-section text-destructive">{zh.errors.network}</div>;
  if (!session || !casePayload)
    return <div className="card card-section text-muted-foreground">{zh.admin.loading}</div>;

  return (
    <CasePage
      casePayload={casePayload}
      condition={session.condition}
      progressCurrent={0}
      progressTotal={session.caseOrder.length}
      practiceBanner
      onLogEvent={(t, p) => logEvent(session.sessionId, t, p)}
      onSubmit={async (result) => {
        await api<ActionResponse>("/api/action", {
          method: "POST",
          body: {
            sessionId: session.sessionId,
            caseId: casePayload.id,
            orderIndex: -1,
            isPractice: true,
            ...result,
          },
        });
        setCaseIndex(0);
        setStep("case");
        router.push("/case/0");
      }}
    />
  );
}
