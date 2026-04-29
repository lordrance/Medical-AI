"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { zh } from "@/lib/i18n/zh-CN";

export function PageBack({ hide }: { hide?: boolean }) {
  const router = useRouter();
  if (hide) return null;
  return (
    <button
      type="button"
      className="btn-ghost mb-4 inline-flex items-center gap-1.5 px-0 text-sm text-muted-foreground hover:text-foreground"
      onClick={() => router.back()}
    >
      <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden />
      {zh.nav.back}
    </button>
  );
}
