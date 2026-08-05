"use client";

/**
 * 全局状态：记住「我是谁、做到第几题、完成码是多少」。
 *
 * 用 zustand + persist：
 *   - zustand 提供跨页面共享的状态（不用一层层传 props）
 *   - persist 自动把状态写进浏览器的 localStorage
 *
 * ★ 为什么必须持久化：整个流程有 12 个页面，手机上刷新一下、
 *   来电话切出去再回来、微信内置浏览器自动回收页面……都会让内存里的
 *   状态清零。存进 localStorage 后，回来还能接着做。
 *
 * ★ 存的是什么：只有 sessionId 这类凭证和进度，**没有**任何答案内容。
 *   答案一提交就立刻发给服务器了。填写中的草稿另外由 persist.ts 管。
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { SessionInfo, SessionPerformance } from "@/lib/api/types";

/** 流程的 6 个阶段。用来判断「这个人现在应该在哪一页」。 */
export type Step =
  | "consent"      // 知情同意
  | "pre_survey"   // 前测问卷
  | "practice"     // 练习题
  | "case"         // 正式题（8 道）
  | "post_survey"  // 后测问卷
  | "completion";  // 完成页

interface StudyState {
  /** 建档时服务器返回的那一整包：sessionId、题目顺序等。null = 还没开始。 */
  session: SessionInfo | null;
  step: Step;
  /** 做到第几道正式题（0~7）。 */
  caseIndex: number;
  /** 完成码，如 "AIDR-1A2B3C4D"。★ 只存在这里，清掉就找不回来了。 */
  completionCode: string | null;
  /** 答对几道的小结，完成页展示用。 */
  performance: SessionPerformance | null;

  // 下面是修改状态的方法。组件里调用它们，所有用到该状态的页面自动重渲染。
  setSession: (s: SessionInfo) => void;
  setStep: (s: Step) => void;
  setCaseIndex: (i: number) => void;
  setCompletionCode: (c: string) => void;
  setPerformance: (p: SessionPerformance | null) => void;
  /** 清空一切，回到最初状态。用于「重新开始」和会话失效自愈。 */
  reset: () => void;
}

export const useStudy = create<StudyState>()(
  persist(
    (set) => ({
      // 初始值
      session: null,
      step: "consent",
      caseIndex: 0,
      completionCode: null,
      performance: null,

      setSession: (session) => set({ session }),
      setStep: (step) => set({ step }),
      setCaseIndex: (caseIndex) => set({ caseIndex }),
      setCompletionCode: (code) => set({ completionCode: code }),
      setPerformance: (performance) => set({ performance }),
      reset: () =>
        set({
          session: null,
          step: "consent",
          caseIndex: 0,
          completionCode: null,
          performance: null,
        }),
    }),
    // localStorage 里的键名。改这个名字 = 所有在做的人进度清零，别乱改。
    { name: "medai-study-v2" },
  ),
);
