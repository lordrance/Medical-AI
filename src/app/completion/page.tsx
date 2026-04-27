"use client";

import { useEffect, useState } from "react";
import { useStudyStore } from "@/lib/session-store";

export default function CompletionPage() {
  const session = useStudyStore((s) => s.session);
  const reset = useStudyStore((s) => s.reset);
  const [code, setCode] = useState<string>("");

  useEffect(() => {
    if (session?.participantId) {
      setCode(`AIDR-${session.participantId.slice(-8).toUpperCase()}`);
    }
  }, [session]);

  return (
    <div className="card space-y-4 p-8 text-center">
      <h2 className="text-2xl font-semibold">Thank you!</h2>
      <p className="text-slate-700">
        Your responses have been recorded. You may now close this window.
      </p>
      {code && (
        <div>
          <p className="text-sm text-slate-500">Completion code</p>
          <code className="mt-1 inline-block rounded bg-slate-100 px-3 py-2 font-mono text-lg text-slate-800">
            {code}
          </code>
        </div>
      )}
      <button className="btn-outline" onClick={reset}>
        Reset (debug)
      </button>
    </div>
  );
}
