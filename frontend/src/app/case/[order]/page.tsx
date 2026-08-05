"use client";

/**
 * 正式题页面。8 道题共用这一个文件，靠网址里的数字区分：
 * /case/0 是第 1 题、/case/7 是第 8 题。（[order] 就是这个可变部分。）
 *
 * 这个文件只负责「取数据 + 跳转」，界面本身在 components/case/CasePage.tsx。
 *
 * ★ 流程只能向前：这里不渲染「返回」按钮。因为服务器保留首次作答，
 *   退回去改答案会「看起来保存了其实没变」，比不给这个选项更糟。
 */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CasePage } from "@/components/case/CasePage";
import { api, isSessionInvalid } from "@/lib/api/client";
import type {
  ActionResponse,
  CaseOpenResponse,
  CaseResponse,
  CasePayload,
} from "@/lib/api/types";
import { logEvent } from "@/lib/logger";
import { useStudy } from "@/lib/store";
import { zh } from "@/lib/i18n/zh-CN";

export default function FormalCasePage() {
  const router = useRouter();
  const params = useParams<{ order: string }>();
  const session = useStudy((s) => s.session);
  const setStep = useStudy((s) => s.setStep);
  const setCaseIndex = useStudy((s) => s.setCaseIndex);
  const reset = useStudy((s) => s.reset);

  // Escape hatch: clear the (possibly dead) persisted session and start over.
  // Without this, a session the backend no longer recognizes 404s forever and
  // "reload" just re-reads the same dead session — a permanent dead-end.
  function restart() {
    reset();
    router.replace("/consent");
  }

  const orderIndex = Number(params.order);
  const [casePayload, setCasePayload] = useState<CasePayload | null>(null);
  const [casePresentationId, setCasePresentationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const casePresentationIdRef = useRef<string | null>(null);

  useEffect(() => {
    casePresentationIdRef.current = casePresentationId;
  }, [casePresentationId]);

  // 这个 useEffect 在「换题」时触发（orderIndex 变了），负责加载题目内容。
  useEffect(() => {
    // 没有会话 = 直接输网址进来的，或者本地数据被清了 → 回到入口
    if (!session) {
      router.replace("/consent");
      return;
    }
    // 网址里的题号不合法（不是数字、越界）→ 说明 8 道题做完了，去后测
    if (
      Number.isNaN(orderIndex) ||
      orderIndex < 0 ||
      orderIndex >= session.caseOrder.length
    ) {
      router.replace("/post-survey");
      return;
    }
    // 清空上一题的残留，否则会闪现上一题的内容
    setCasePayload(null);
    setCasePresentationId(null);
    setError(null);
    setCaseIndex(orderIndex);
    // 从建档时拿到的题目顺序里取出这一题的 ID
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
        if (cancelled) return;
        // Dead session → auto-reset and restart, instead of an infinite
        // reload loop against a session the backend no longer knows.
        if (isSessionInvalid(e)) {
          restart();
          return;
        }
        setError((e as Error).message);
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
        <div className="flex justify-center gap-3">
          <button className="btn-primary" onClick={() => window.location.reload()}>
            {zh.caseUI.retry}
          </button>
          <button
            className="rounded-md border border-border px-4 py-2 text-sm"
            onClick={restart}
          >
            {zh.errors.restart}
          </button>
        </div>
      </div>
    );
  if (!session || !casePayload)
    return <div className="card card-section text-muted-foreground">{zh.admin.loading}</div>;

  const total = session.caseOrder.length;

  return (
    <>
      {/* No back button during the cases: the study is forward-only. The
          server keeps the first answer for a case, so going back and
          re-answering would look like it saved but silently change nothing. */}
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
      // 医生点「提交」时 CasePage 会调这个函数。
      // ★ 注意这里故意不 try/catch：出错要让异常往上抛给 CasePage，
      // 它才能显示「提交失败」并让医生重试。而且只有成功才会走到下面的
      // 跳转——失败就停在原地，答案不会丢。
      onSubmit={async (result) => {
        await api<ActionResponse>("/api/action", {
          method: "POST",
          body: {
            sessionId: session.sessionId,
            caseId: casePayload.id,
            orderIndex,
            isPractice: false,
            ...result,  // CasePage 收集的选择、文本、理由、量表、行为数据
          },
        });
        // 提交成功 → 下一题；已经是最后一题 → 去后测问卷
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
