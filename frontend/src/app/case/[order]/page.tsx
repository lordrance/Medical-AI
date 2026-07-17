"use client";

import { useParams, useRouter } from "next/navigation";
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

export default function FormalCasePage() {
  const router = useRouter();
  const params = useParams<{ order: string }>();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const setCaseIndex = useStudy((s) => s.setCaseIndex);

  const orderIndex = Number(params.order);
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
    if (
      Number.isNaN(orderIndex) ||
      orderIndex < 0 ||
      orderIndex >= session.caseOrder.length
    ) {
      router.replace("/post-survey");
      return;
    }
    setCasePayload(null);
    setCasePresentationId(null);
    setError(null);
    setCaseIndex(orderIndex);
    const caseId = session.caseOrder[orderIndex];
    // Guard against a stale response landing after the participant already
    // navigated to another case (rapid next-clicks / back-forward).
    let cancelled = false;
    void (async () => {
      // Step 1: load the case content. Only THIS failing should block the case.
      try {
        const cr = await api<CaseResponse>(`/api/case/${caseId}`, {
          query: { sessionId: session.sessionId },
        });
        if (cancelled) return;
        setCasePayload(cr.case);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
        return;
      }
      // Step 2: open the presentation — telemetry-only correlation id. If it
      // fails (flaky network), the case is still fully usable; do NOT block
      // rendering on it. answer submission does not need casePresentationId.
      try {
        const op = await api<CaseOpenResponse>("/api/case/open", {
          method: "POST",
          body: { sessionId: session.sessionId, caseId, orderIndex },
        });
        if (!cancelled) setCasePresentationId(op.casePresentationId);
      } catch {
        // telemetry degradation only; ignore.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, orderIndex, router, setCaseIndex]);

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

  const total = session.caseOrder.length;

  return (
    <>
      <PageBack />
      <CasePage
        casePayload={casePayload}
        progressCurrent={orderIndex + 1}
        progressTotal={total}
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
    </>
  );
}
