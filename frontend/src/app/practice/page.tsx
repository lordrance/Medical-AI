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
    setError(null);
    let cancelled = false;
    void (async () => {
      // Step 1: load case content — only this failing blocks the page.
      try {
        const cr = await api<CaseResponse>(
          `/api/case/${session.practiceCaseId}`,
          {
            query: { sessionId: session.sessionId },
          },
        );
        if (cancelled) return;
        setCasePayload(cr.case);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
        return;
      }
      // Step 2: telemetry open — non-blocking.
      try {
        const op = await api<CaseOpenResponse>("/api/case/open", {
          method: "POST",
          body: {
            sessionId: session.sessionId,
            caseId: session.practiceCaseId,
            orderIndex: -1,
          },
        });
        if (!cancelled) setCasePresentationId(op.casePresentationId);
      } catch {
        // telemetry only; ignore.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, router]);

  if (error)
    return (
      <div className="card card-section space-y-3 text-center">
        <p className="text-destructive">{zh.errors.network}</p>
        <button className="btn-primary" onClick={() => window.location.reload()}>
          {zh.caseUI.retry}
        </button>
      </div>
    );
  if (!session || !casePayload)
    return <div className="card card-section text-muted-foreground">{zh.admin.loading}</div>;

  return (
    <>
      <PageBack />
      <CasePage
        casePayload={casePayload}
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
