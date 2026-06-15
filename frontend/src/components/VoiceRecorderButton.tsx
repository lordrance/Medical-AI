"use client";

/**
 * V4: MediaRecorder-based audio capture for L1/L2/L3 open-ended items.
 *
 * Distinct from `VoiceInputButton.tsx` — that one uses the Web Speech API
 * to transcribe live speech into a text field. This one records the raw
 * audio for offline human transcription. The use cases don't overlap:
 *   - VoiceInputButton  → dictate text into the final-reply textarea
 *   - VoiceRecorderButton → keep the audio itself as a research artefact
 *
 * Flow: idle → recording → uploading → done. Errors surface inline with
 * a clear message; participants can retry. One recording per question is
 * supported; re-recording uploads a new row server-side (admin can keep
 * the latest or all — the index.csv export carries created_at).
 *
 * V5: Upload retry — on network errors (TypeError), retries up to 2 times
 * with exponential backoff (500ms, 1000ms) and shows progress to the user.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import { buildFetchUrl } from "@/lib/api/client";

type Status = "idle" | "recording" | "uploading" | "done" | "error";

interface UploadProgress {
  attempt: number;
  maxAttempts: number;
}

export interface VoiceRecorderButtonProps {
  sessionId: string;
  questionId: string;
  /** Optional callback after a successful upload (e.g. log a ui_event). */
  onUploaded?: (info: { voiceRecordingId: string; bytes: number }) => void;
  className?: string;
}

export function VoiceRecorderButton({
  sessionId,
  questionId,
  onUploaded,
  className,
}: VoiceRecorderButtonProps) {
  const [mounted, setMounted] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [lastBytes, setLastBytes] = useState<number | null>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number>(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => setMounted(true), []);

  const supported =
    mounted &&
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function";

  const cleanup = useCallback(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    const stream = streamRef.current;
    streamRef.current = null;
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    recorderRef.current = null;
    chunksRef.current = [];
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  /** Upload blob with retry for network errors. */
  const uploadWithRetry = useCallback(
    async (blob: Blob, durationMs: number) => {
      const maxAttempts = 2; // retry up to 2 times after the initial attempt

      for (let attempt = 0; ; attempt++) {
        try {
          if (attempt > 0) {
            setUploadProgress({ attempt, maxAttempts });
          }

          const fd = new FormData();
          fd.append("sessionId", sessionId);
          fd.append("questionId", questionId);
          fd.append("durationMs", String(durationMs));
          fd.append("audio", blob, `recording.${extFromMime(blob.type)}`);
          const r = await fetch(buildFetchUrl("/api/voice-recording"), {
            method: "POST",
            body: fd,
          });
          if (!r.ok) {
            throw new Error(`上传失败 (HTTP ${r.status})`);
          }
          const j = (await r.json()) as {
            voiceRecordingId: string;
            fileSizeBytes: number;
          };
          setStatus("done");
          setUploadProgress(null);
          setLastBytes(j.fileSizeBytes);
          onUploaded?.({
            voiceRecordingId: j.voiceRecordingId,
            bytes: j.fileSizeBytes,
          });
          return; // success
        } catch (e) {
          const isNetworkError =
            e instanceof TypeError ||
            (e instanceof Error && e.name === "TypeError");

          if (!isNetworkError || attempt >= maxAttempts) {
            // Non-network error, or all retries exhausted
            setStatus("error");
            setUploadProgress(null);
            setErrorMsg((e as Error).message);
            return;
          }

          // Network error — wait before retrying (exponential backoff)
          await new Promise((r) => setTimeout(r, 500 * Math.pow(2, attempt)));
        }
      }
    },
    [sessionId, questionId, onUploaded],
  );

  const start = useCallback(async () => {
    if (!supported || status === "recording" || status === "uploading") return;
    setErrorMsg(null);
    setStatus("recording");
    setElapsedMs(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream);
      recorderRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      mr.onstop = () => {
        const duration = Date.now() - startedAtRef.current;
        const mime = chunksRef.current[0]?.type || mr.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mime });
        cleanup();
        void uploadWithRetry(blob, duration);
      };
      startedAtRef.current = Date.now();
      mr.start();
      tickRef.current = setInterval(() => {
        setElapsedMs(Date.now() - startedAtRef.current);
      }, 250);
    } catch (e) {
      setStatus("error");
      const name = (e as { name?: string }).name;
      if (name === "NotAllowedError") {
        setErrorMsg("麦克风权限被拒绝，请在浏览器设置中允许本站使用麦克风后重试。");
      } else if (name === "NotFoundError") {
        setErrorMsg("未检测到可用的麦克风设备。");
      } else {
        setErrorMsg((e as Error).message || "无法启动录音。");
      }
      cleanup();
    }
  }, [cleanup, status, supported, uploadWithRetry]);

  const stop = useCallback(() => {
    const mr = recorderRef.current;
    if (mr && mr.state !== "inactive") {
      mr.stop(); // triggers onstop → uploadWithRetry
    }
  }, []);

  if (!supported) {
    return (
      <p className={cn("text-xs text-muted-foreground", className)}>
        当前浏览器不支持录音；请在 Chrome / Edge / Safari 中打开此页面。
      </p>
    );
  }

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {status === "recording" ? (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-md border border-destructive/60 bg-destructive/10 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20"
            onClick={stop}
            aria-label="停止录音"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
            停止录音
          </button>
        ) : (
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            onClick={start}
            disabled={status === "uploading"}
            aria-label={status === "done" ? "重新录音" : "开始录音"}
          >
            {status === "uploading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Mic className="h-3.5 w-3.5" />
            )}
            {status === "uploading"
              ? uploadProgress
                ? `上传失败，正在重试 (${uploadProgress.attempt}/${uploadProgress.maxAttempts})…`
                : "上传中…"
              : status === "done"
                ? "重新录音"
                : "开始录音"}
          </button>
        )}

        {status === "recording" && (
          <span className="text-xs text-destructive">
            正在录音 {formatMs(elapsedMs)}
          </span>
        )}
        {status === "done" && lastBytes !== null && (
          <span className="inline-flex items-center gap-1 text-xs text-foreground/70">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            已保存（{formatBytes(lastBytes)}）
          </span>
        )}
        {status === "error" && errorMsg && (
          <span className="inline-flex items-center gap-1 text-xs text-destructive">
            <AlertTriangle className="h-3.5 w-3.5" />
            {errorMsg}
          </span>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground">
        录音将与文字回答一起提交给研究团队，并在事后由人工转写。可不录音，或重新录音覆盖。
      </p>
    </div>
  );
}

function extFromMime(mime: string): string {
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("mpeg")) return "mp3";
  if (mime.includes("wav")) return "wav";
  return "bin";
}

function formatMs(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
}
