"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  appendVoiceTranscript,
  getSpeechRecognitionConstructor,
  type SpeechRecognitionLike,
} from "@/lib/speechRecognition";
import { zh } from "@/lib/i18n/zh-CN";

export type VoiceInputButtonProps = {
  /** 当前输入框全文；每有一段 final 识别结果会与其合并后回传。 */
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  className?: string;
  /** 用于 ui_events：开始/结束/错误（不含识别正文）。 */
  onVoiceActivity?: (
    kind: "started" | "ended" | "error",
    detail?: { code?: string },
  ) => void;
};

export function VoiceInputButton({
  value,
  onChange,
  disabled,
  className,
  onVoiceActivity,
}: VoiceInputButtonProps) {
  const [mounted, setMounted] = useState(false);
  const [listening, setListening] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const listeningRef = useRef(false);
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => setMounted(true), []);

  const supported = mounted && getSpeechRecognitionConstructor() !== null;

  const stopInternal = useCallback(() => {
    const r = recRef.current;
    recRef.current = null;
    if (r) {
      try {
        r.stop();
      } catch {
        try {
          r.abort();
        } catch {
          /* ignore */
        }
      }
    }
    listeningRef.current = false;
    setListening(false);
    setHint(null);
  }, []);

  useEffect(() => () => stopInternal(), [stopInternal]);

  const start = useCallback(() => {
    const Ctor = getSpeechRecognitionConstructor();
    if (!Ctor || disabled) return;
    stopInternal();
    const rec = new Ctor();
    rec.lang = "zh-CN";
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      listeningRef.current = true;
      setListening(true);
      setHint(zh.voiceInput.listening);
      onVoiceActivity?.("started");
    };

    rec.onerror = (ev: Event) => {
      const raw = ev as { error?: string };
      const code = raw.error ?? "unknown";
      let msg: string = zh.voiceInput.errorGeneric;
      if (code === "not-allowed" || code === "service-not-allowed") {
        msg = zh.voiceInput.errorDenied;
      } else if (code === "no-speech") {
        msg = zh.voiceInput.errorNoSpeech;
      } else if (code === "network") {
        msg = zh.voiceInput.errorNetwork;
      }
      setHint(msg);
      onVoiceActivity?.("error", { code });
      listeningRef.current = false;
      setListening(false);
      recRef.current = null;
    };

    rec.onend = () => {
      listeningRef.current = false;
      setListening(false);
      setHint((h) => (h === zh.voiceInput.listening ? null : h));
      onVoiceActivity?.("ended");
      recRef.current = null;
    };

    rec.onresult = (ev: Event) => {
      const r = ev as unknown as {
        resultIndex: number;
        results: {
          length: number;
          [index: number]: { 0: { transcript: string }; isFinal: boolean };
        };
      };
      let interim = "";
      let finals = "";
      for (let i = r.resultIndex; i < r.results.length; i++) {
        const row = r.results[i];
        const piece = row?.[0]?.transcript ?? "";
        if (row.isFinal) finals += piece;
        else interim += piece;
      }
      if (finals) {
        const next = appendVoiceTranscript(valueRef.current, finals);
        onChange(next);
      }
      if (interim.trim()) {
        setHint(`${zh.voiceInput.listening} ${interim.trim()}`);
      } else if (listeningRef.current) {
        setHint(zh.voiceInput.listening);
      }
    };

    recRef.current = rec;
    try {
      rec.start();
    } catch {
      setHint(zh.voiceInput.errorStart);
      onVoiceActivity?.("error", { code: "start-failed" });
      recRef.current = null;
      listeningRef.current = false;
      setListening(false);
    }
  }, [disabled, onChange, onVoiceActivity, stopInternal]);

  const toggle = useCallback(() => {
    setHint(null);
    if (listening) {
      stopInternal();
      return;
    }
    start();
  }, [listening, start, stopInternal]);

  if (!supported) return null;

  return (
    <div className={cn("flex flex-col items-end gap-1", className)}>
      <button
        type="button"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors",
          listening
            ? "border-destructive/60 bg-destructive/10 text-destructive"
            : "border-border bg-muted/50 text-foreground hover:bg-muted",
        )}
        disabled={disabled}
        onClick={toggle}
        aria-pressed={listening}
        aria-label={listening ? zh.voiceInput.stop : zh.voiceInput.start}
      >
        {listening ? (
          <Square className="h-3.5 w-3.5 fill-current" aria-hidden />
        ) : (
          <Mic className="h-3.5 w-3.5" aria-hidden />
        )}
        {listening ? zh.voiceInput.stop : zh.voiceInput.start}
      </button>
      {hint && (
        <p className="max-w-[min(100%,20rem)] text-right text-[11px] text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}
