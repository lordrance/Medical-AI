"use client";

/**
 * 知情同意页 —— 研究的正式入口。
 *
 * 医生勾选「我已阅读并同意」后点开始，这里会向服务器建档，
 * 拿到 sessionId 存进浏览器，然后进入前测问卷。
 *
 * ★ 这是唯一一个「创建会话」的地方。之后所有页面都假定 session 已存在，
 *   发现不存在就把人送回这里。
 */

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api/client";
import type { SessionInfo } from "@/lib/api/types";
import { zh } from "@/lib/i18n/zh-CN";
import { useStudy } from "@/lib/store";
import { PageBack } from "@/components/PageBack";

export default function ConsentPage() {
  const router = useRouter();
  // 从全局状态里取出要用的几个方法（zustand 的写法）
  const setSession = useStudy((s) => s.setSession);
  const setStep = useStudy((s) => s.setStep);
  const reset = useStudy((s) => s.reset);

  const [agreed, setAgreed] = useState(false);   // 勾选框有没有勾
  const [busy, setBusy] = useState(false);       // 正在请求中（按钮转圈、禁止重复点）
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      // ★ 先 reset()：万一浏览器里还留着上一次没做完的会话，
      // 不清掉的话新旧数据会串在一起。
      reset();
      const s = await api<SessionInfo>("/api/session", { method: "POST" });
      setSession(s);            // 存进 localStorage，之后每个请求都要用
      setStep("pre_survey");
      router.push("/pre-survey");
    } catch (e) {
      // 区分两种错误给不同提示：服务器明确返回了错误码 vs 根本没连上。
      // 带上 HTTP 状态码，方便医生截图反馈时我们定位问题。
      setError(
        e instanceof ApiError ? `${zh.consent.failed}：HTTP ${e.status}` : zh.errors.network,
      );
    } finally {
      // finally 保证无论成功失败都解除按钮的禁用状态，
      // 否则出错后按钮永远是灰的，医生就卡死在这一页了。
      setBusy(false);
    }
  }

  return (
    <div className="card card-section animate-slide-up">
      <PageBack />
      <h2 className="text-xl font-semibold">{zh.consent.title}</h2>
      <div className="mt-5 space-y-3 text-sm leading-7 text-foreground/85">
        <p>{zh.consent.p1}</p>
        <p>{zh.consent.p2}</p>
        <p>{zh.consent.p3}</p>
        <p className="rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-foreground">
          {zh.consent.p4}
        </p>
        <p className="font-medium text-foreground">{zh.consent.checklistIntro}</p>
        <ul className="list-disc space-y-1.5 pl-5">
          {zh.consent.checklistBullets.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </div>

      <label className="mt-7 flex cursor-pointer items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1 h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
        />
        <span>{zh.consent.agree}</span>
      </label>

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

      <div className="mt-7 flex justify-end">
        <button className="btn-primary" disabled={!agreed || busy} onClick={start}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {busy ? zh.consent.starting : zh.consent.cta}
        </button>
      </div>
    </div>
  );
}
