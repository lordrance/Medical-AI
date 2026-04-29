"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { SessionInfo, SessionPerformance } from "@/lib/api/types";

export type Step =
  | "consent"
  | "pre_survey"
  | "practice"
  | "case"
  | "post_survey"
  | "completion";

interface StudyState {
  session: SessionInfo | null;
  step: Step;
  caseIndex: number;
  completionCode: string | null;
  performance: SessionPerformance | null;
  setSession: (s: SessionInfo) => void;
  setStep: (s: Step) => void;
  setCaseIndex: (i: number) => void;
  setCompletionCode: (c: string) => void;
  setPerformance: (p: SessionPerformance | null) => void;
  reset: () => void;
}

export const useStudy = create<StudyState>()(
  persist(
    (set) => ({
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
    { name: "medai-study-v2" },
  ),
);
