"use client";

/**
 * 返回上一页的按钮。
 *
 * ★ 现在只有 /consent 页在用。答题过程（练习题 + 8 道正式题）
 * 和前后测问卷都**不显示**它——流程是单向的：服务器保留首次作答，
 * 退回去改答案会「看起来保存了其实没变」，比不给这个选项更糟。
 *
 * hide 参数是历史遗留：早期页面用 <PageBack hide /> 来隐藏，
 * 现在直接不渲染这个组件了。
 */

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
