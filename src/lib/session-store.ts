"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Condition, SessionInfo } from "./types";

interface StudyState {
  session: SessionInfo | null;
  step:
    | "consent"
    | "pre_survey"
    | "practice"
    | "case"
    | "post_survey"
    | "completion";
  caseIndex: number;

  setSession: (s: SessionInfo) => void;
  setStep: (s: StudyState["step"]) => void;
  setCaseIndex: (i: number) => void;
  reset: () => void;
}

export const useStudyStore = create<StudyState>()(
  persist(
    (set) => ({
      session: null,
      step: "consent",
      caseIndex: 0,
      setSession: (session) => set({ session }),
      setStep: (step) => set({ step }),
      setCaseIndex: (caseIndex) => set({ caseIndex }),
      reset: () => set({ session: null, step: "consent", caseIndex: 0 }),
    }),
    { name: "study-state-v1" },
  ),
);

export type { Condition };
