export type DictationStatus = "idle" | "starting" | "recording" | "transcribing";
export interface TranscriptionEndpoint { baseUrl: string; apiKey: string; model: string }
interface Options {
  onStatus: (status: DictationStatus) => void;
  onTranscript: (text: string) => void;
  onError: (error: Error) => void;
  onEnd: (cancelled: boolean) => void;
  requestTimeout?: number;
  maxRecording?: number;
}
interface Session {
  controller: AbortController;
  timer: ReturnType<typeof setTimeout>;
  tracks?: MediaStream;
  recorder?: MediaRecorder;
  recognition?: any;
  started?: number;
}

/** A forgotten microphone stops by itself; what was said is still recognized. The service takes up to 6 minutes. */
const MAX_RECORDING = 5 * 60_000;
/** The PC recognizes a second of speech in about 0.16 s (5 minutes in 47 s); the wait allows about twice that. */
const RECOGNITION_PER_SECOND = 0.3;

/** Own cancellable lifecycle: Canvas's hook exposes no abort or timeout for STT. */
export class DictationSession {
  status: DictationStatus = "idle";
  private current: Session | null = null;
  private options: Options;
  constructor(options: Options) { this.options = options; }
  private statusChanged(status: DictationStatus) { this.status = status; this.options.onStatus(status); }
  private deadline(session: Session, milliseconds: number, message = "Распознавание не ответило вовремя. Попробуйте ещё раз.") {
    clearTimeout(session.timer);
    session.timer = setTimeout(() => this.end(true, new Error(message)), milliseconds);
  }
  private end(cancelled: boolean, error?: Error, text?: string) {
    const session = this.current;
    if (!session) return;
    this.current = null;
    clearTimeout(session.timer);
    session.controller.abort();
    if (session.recorder) {
      session.recorder.onstop = null; session.recorder.onerror = null; session.recorder.ondataavailable = null;
      try { if (session.recorder.state !== "inactive") session.recorder.stop(); } catch { /* Tracks still get closed below. */ }
    }
    if (session.recognition) {
      session.recognition.onend = null; session.recognition.onerror = null;
      try { session.recognition.abort(); } catch { /* End can race the browser's own end callback. */ }
    }
    session.tracks?.getTracks().forEach(track => { try { track.stop(); } catch { /* Always release the speech hold. */ } });
    this.statusChanged("idle");
    this.options.onEnd(cancelled);
    if (error) this.options.onError(error);
    if (!cancelled && text?.trim()) this.options.onTranscript(text.trim());
  }
  /** A long dictation takes longer to recognize: a fixed wait would cut off a three-minute one. */
  private recognitionWait(session: Session) {
    return (this.options.requestTimeout ?? 30000) + (Date.now() - (session.started ?? Date.now())) * RECOGNITION_PER_SECOND;
  }
  private stopRecording(session: Session) {
    if (this.current !== session || this.status !== "recording") return;
    this.statusChanged("transcribing");
    this.deadline(session, this.recognitionWait(session));
    try { session.recorder?.stop(); session.recognition?.stop(); }
    catch { this.end(true, new Error("Не удалось остановить запись. Попробуйте ещё раз.")); }
  }
  cancel = () => this.end(true);
  toggle(endpoint: TranscriptionEndpoint) {
    if (this.status === "recording") this.stopRecording(this.current!);
    else if (this.status !== "idle") this.cancel();
    else void this.start(endpoint);
  }
  private async start(endpoint: TranscriptionEndpoint) {
    const controller = new AbortController();
    const session: Session = { controller, timer: 0 as unknown as ReturnType<typeof setTimeout> };
    this.current = session;
    this.statusChanged("starting");
    this.deadline(session, this.options.requestTimeout ?? 30000, "Браузер не открыл микрофон вовремя. Попробуйте ещё раз.");
    try {
      if (!endpoint.baseUrl) {
        const Constructor = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
        if (!Constructor) throw new Error("Браузер не поддерживает диктовку");
        const recognition = new Constructor();
        session.recognition = recognition;
        recognition.continuous = true; recognition.interimResults = false;
        recognition.lang = "ru-RU";
        let text = "";
        recognition.onresult = (event: any) => { text = Array.from(event.results as ArrayLike<any>, result => result[0].transcript).join(" "); };
        recognition.onend = () => { if (this.current === session) this.end(false, undefined, text); };
        recognition.onerror = () => { if (this.current === session) this.end(true, new Error("Не удалось распознать речь. Проверьте доступ к микрофону.")); };
        recognition.start();
      } else {
        const permission = navigator.mediaDevices.getUserMedia({audio: true});
        // A dismissed permission prompt can resolve after Cancel/timeout. Stop those tracks too.
        permission.then(stream => { if (this.current !== session) stream.getTracks().forEach(track => track.stop()); }, () => {});
        const stream = await permission;
        if (this.current !== session) return;
        session.tracks = stream;
        const recorder = new MediaRecorder(stream);
        session.recorder = recorder;
        const chunks: Blob[] = [];
        recorder.ondataavailable = event => chunks.push(event.data);
        recorder.onerror = () => { if (this.current === session) this.end(true, new Error("Не удалось записать речь. Попробуйте ещё раз.")); };
        recorder.onstop = async () => {
          if (this.current !== session) return;
          stream.getTracks().forEach(track => track.stop());
          this.statusChanged("transcribing");
          this.deadline(session, this.recognitionWait(session));
          try {
            const blob = new Blob(chunks, {type: recorder.mimeType});
            const data = new FormData();
            data.append("file", blob, `dictation.${blob.type.split(/[/;]/)[1] || "webm"}`);
            data.append("model", endpoint.model || "whisper-1");
            const response = await fetch(`${endpoint.baseUrl.replace(/\/+$/, "")}/audio/transcriptions`, {
              method: "POST", body: data, signal: controller.signal,
              headers: endpoint.apiKey ? {Authorization: `Bearer ${endpoint.apiKey}`} : undefined,
            });
            if (!response.ok) throw new Error("Сервис распознавания недоступен. Попробуйте ещё раз.");
            const result = await response.json();
            if (typeof result.text !== "string") throw new Error("Сервис вернул неверный результат распознавания");
            if (this.current === session) this.end(false, undefined, result.text);
          } catch (error) {
            if (this.current === session) this.end(true, error instanceof Error ? error : new Error("Не удалось распознать речь"));
          }
        };
        recorder.start();
      }
      if (this.current === session) {
        // Recording lasts until Stop/Cancel, or the limit for a microphone left on.
        clearTimeout(session.timer);
        session.started = Date.now();
        session.timer = setTimeout(() => this.stopRecording(session), this.options.maxRecording ?? MAX_RECORDING);
        this.statusChanged("recording");
      }
    } catch {
      if (this.current === session) this.end(true, new Error("Нет доступа к микрофону. Разрешите его в настройках браузера."));
    }
  }
}
