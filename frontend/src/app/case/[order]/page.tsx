"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CasePage } from "@/components/case/CasePage";
import { api } from "@/lib/api/client";
import type { ActionResponse, CaseResponse, CasePayload } from "@/lib/api/types";
import { logEvent } from "@/lib/logger";
import { useStudy } from "@/lib/store";
import { zh } from "@/lib/i18n/zh-CN";

export default function FormalCasePage() {
  const router = useRouter();
  const params = useParams<{ order: string }>();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const setCaseIndex = useStudy((s) => s.setCaseIndex);

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
    void api<CaseResponse>(`/api/case/${caseId}`, {
      query: { sessionId: session.sessionId },
    })
      .then((r) => setCasePayload(r.case))
      .catch((e) => setError((e as Error).message));
  }, [session, orderIndex, router, setCaseIndex]);

  if (error) return <div className="card card-section text-destructive">{zh.errors.network}</div>;
  if (!session || !casePayload)
    return <div className="card card-section text-muted-foreground">{zh.admin.loading}</div>;

  const total = session.caseOrder.length;

  return (
    <CasePage
      casePayload={casePayload}
      condition={session.condition}
      progressCurrent={orderIndex + 1}
      progressTotal={total}
      onLogEvent={(t, p) => logEvent(session.sessionId, t, p)}
      onSubmit={async (result) => {
        await api<ActionResponse>("/api/action", {
          method: "POST",
          body: {
            sessionId: session.sessionId,
            caseId: casePayload.id,
            orderIndex,
            isPractice: false,
            ...result,
          },
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
