"use client";

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
  const setSession = useStudy((s) => s.setSession);
  const setStep = useStudy((s) => s.setStep);
  const reset = useStudy((s) => s.reset);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      reset();
      const s = await api<SessionInfo>("/api/session", { method: "POST" });
      setSession(s);
      setStep("pre_survey");
      router.push("/pre-survey");
    } catch (e) {
      setError(
        e instanceof ApiError ? `${zh.consent.failed}：HTTP ${e.status}` : zh.errors.network,
      );
    } finally {
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
