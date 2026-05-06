"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CasePage } from "@/components/case/CasePage";
import { api } from "@/lib/api/client";
import type {
  ActionResponse,
  CaseOpenResponse,
  CaseResponse,
  CasePayload,
} from "@/lib/api/types";
import { logEvent } from "@/lib/logger";
import { useStudy } from "@/lib/store";
import { zh } from "@/lib/i18n/zh-CN";
import { PageBack } from "@/components/PageBack";

export default function PracticePage() {
  const router = useRouter();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const setCaseIndex = useStudy((s) => s.setCaseIndex);
  const [casePayload, setCasePayload] = useState<CasePayload | null>(null);
  const [casePresentationId, setCasePresentationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const casePresentationIdRef = useRef<string | null>(null);

  useEffect(() => {
    casePresentationIdRef.current = casePresentationId;
  }, [casePresentationId]);

  useEffect(() => {
    if (!session) {
      router.replace("/consent");
      return;
    }
    setCasePayload(null);
    setCasePresentationId(null);
    void (async () => {
      try {
        const cr = await api<CaseResponse>(
          `/api/case/${session.practiceCaseId}`,
          {
            query: { sessionId: session.sessionId },
          },
        );
        setCasePayload(cr.case);
        const op = await api<CaseOpenResponse>("/api/case/open", {
          method: "POST",
          body: {
            sessionId: session.sessionId,
            caseId: session.practiceCaseId,
            orderIndex: -1,
          },
        });
        setCasePresentationId(op.casePresentationId);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [session, router]);

  if (error) return <div className="card card-section text-destructive">{zh.errors.network}</div>;
  if (!session || !casePayload)
    return <div className="card card-section text-muted-foreground">{zh.admin.loading}</div>;

  return (
    <>
      <PageBack />
      <CasePage
        casePayload={casePayload}
        condition={session.condition}
        progressCurrent={0}
        progressTotal={session.caseOrder.length}
        practiceBanner
        casePresentationId={casePresentationId}
        onLogEvent={(t, p) =>
          logEvent(
            session.sessionId,
            t,
            p,
            casePresentationIdRef.current ?? undefined,
          )
        }
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
    </>
  );
}
