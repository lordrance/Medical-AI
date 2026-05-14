/** 浏览器内置语音识别（Web Speech API），无需单独付费 API Key。 */

export type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

export interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives?: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: ((this: SpeechRecognitionLike, ev: Event) => void) | null;
  onend: ((this: SpeechRecognitionLike, ev: Event) => void) | null;
  onerror: ((this: SpeechRecognitionLike, ev: Event) => void) | null;
  onresult: ((this: SpeechRecognitionLike, ev: Event) => void) | null;
}

export function getSpeechRecognitionConstructor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** 将识别片段拼入已有文本：自动补空格，避免粘在一起。 */
export function appendVoiceTranscript(prev: string, chunk: string): string {
  const t = chunk.replace(/\s+/g, " ").trim();
  if (!t) return prev;
  if (!prev) return t;
  const needsSpace = !/\s$/.test(prev) && !/^\s/.test(t);
  return needsSpace ? `${prev} ${t}` : `${prev}${t}`;
}
