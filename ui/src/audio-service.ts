import { useSyncExternalStore } from "react";
import { forSpeech, speechChunks } from "./speech-events.ts";
import { getPreferences, setPreferences } from "./preferences.ts";
import { errorMessage } from "./errors.ts";

export interface AudioStatus {
  /** Answer being fetched or played; the ▶ of this answer shows ■. */
  currentId: string | null;
  /** The browser allowed playback (a gesture happened); a refused play() takes it back. */
  isUnlocked: boolean;
  error: string;
  isDictating: boolean;
}

/** full: «Полностью» — the voice service then reads links, paths and hashes out too. */
interface Item { id: string; chunks: string[]; full?: boolean }

/** Status id of an answer being read in full; ▶ and «полностью» show ■ separately. */
export const fullReadingId = (id: string) => `${id}:full`;

const SILENT_WAV = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQQAAAAAAAAA";

class AudioService {
  private audio: HTMLAudioElement | null = null;
  /** Parts alternate between the two: the next one is decoded while the current plays (no gap at the seam). */
  private spare: HTMLAudioElement | null = null;
  private controller: AbortController | null = null;
  private queue: Item[] = [];
  private pendingStep: Item | null = null;
  private currentIsStep = false;
  /** Answers already read or asked for: automatic reading never repeats them, ▶ may. */
  private handled = new Set<string>();
  private generation = 0;
  private unlocking = false;
  private dictations = new Map<symbol, (() => void) | undefined>();
  private deferredAnswers = new Map<string, string>();
  private status: AudioStatus = { currentId: null, isUnlocked: false, error: "", isDictating: false };
  private listeners = new Set<() => void>();

  constructor() {
    // Lock screen, notification and headset buttons: without handlers their "pause" would
    // freeze the reading half-way instead of stopping it.
    const session = globalThis.navigator?.mediaSession;
    if (!session) return;
    for (const action of ["pause", "stop"] as const) session.setActionHandler(action, () => this.stop());
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getStatus = () => this.status;

  setAutoSpeak(enabled: boolean) {
    setPreferences({ autoSpeak: enabled });
    if (!enabled) this.stop();
  }

  /** Hold from before microphone permission until dictation ends, fails or unmounts. */
  beginDictation(cancel?: () => void) {
    const deferred = new Map(this.deferredAnswers);
    const token = Symbol();
    this.dictations.set(token, cancel);
    this.notify({ isDictating: true });
    this.stop();
    this.deferredAnswers = deferred;
    return (readDeferred = false) => {
      if (!this.dictations.delete(token)) return;
      this.notify({ isDictating: this.dictations.size > 0 });
      if (this.dictations.size) return;
      const answers = [...this.deferredAnswers];
      this.deferredAnswers.clear();
      if (readDeferred) for (const [id, text] of answers) this.speak(id, text);
    };
  }

  cancelDictation() {
    for (const cancel of [...this.dictations.values()]) cancel?.();
  }

  private notify(update: Partial<AudioStatus>) {
    this.status = { ...this.status, ...update };
    const session = globalThis.navigator?.mediaSession;
    if (session) session.playbackState = this.status.currentId ? "playing" : "none";
    for (const listener of this.listeners) listener();
  }

  /** Call from a trusted user gesture: browsers allow playback only after one. */
  async unlockAudio() {
    if (this.unlocking || this.status.isUnlocked || this.status.isDictating) return;
    this.unlocking = true;
    this.audio ??= new Audio();
    this.spare ??= new Audio();
    const players = [this.audio, this.spare];
    // Reuse the same elements for unlock and speech; stop() leaves an unlock alone.
    for (const player of players) player.src = SILENT_WAV;
    try {
      await Promise.all(players.map((player) => player.play()));
      for (const player of players) {
        player.pause();
        player.removeAttribute("src");
      }
      this.notify({ isUnlocked: true, error: "" });
      void this.processQueue();
    } catch {
      // A refused ▶ must not start by surprise after some later gesture.
      this.queue = [];
      this.notify({ isUnlocked: false, error: "Браузер пока не разрешил звук. Нажмите «Включить звук»." });
    } finally {
      this.unlocking = false;
    }
  }

  /** Automatic reading: once per answer, never a hidden backlog before sound is allowed. */
  speak(id: string, text: string) {
    if (!getPreferences().autoSpeak || !this.status.isUnlocked || this.handled.has(id)) return;
    if (this.status.isDictating) { this.deferredAnswers.set(id, text); return; }
    const chunks = speechChunks(forSpeech(text, false));
    if (!chunks.length) return;
    this.handled.add(id);
    const item: Item = { id, chunks };
    if (this.currentIsStep) {
      this.interruptStep();
      this.queue.unshift(item);
      void this.processQueue();
      return;
    }
    this.queue.push(item);
    void this.processQueue();
  }

  /** Intermediate action step: latest phrase replaces waiting one; stops if answer sounds. */
  speakStep(id: string, text: string) {
    const prefs = getPreferences();
    if (!prefs.autoSpeak || !prefs.speakSteps || !this.status.isUnlocked || this.status.isDictating || this.handled.has(id)) return;
    if (this.status.currentId && !this.currentIsStep) return;
    const chunks = speechChunks(forSpeech(text, false));
    if (!chunks.length) return;
    this.handled.add(id);
    this.pendingStep = { id, chunks };
    if (!this.status.currentId) {
      void this.processQueue();
    }
  }

  private interruptStep() {
    this.generation++;
    this.controller?.abort();
    this.controller = null;
    this.silence();
    this.pendingStep = null;
    this.currentIsStep = false;
    this.notify({ currentId: null });
  }

  private silence() {
    for (const player of [this.audio, this.spare]) {
      if (!player || player.src === SILENT_WAV) continue;
      player.pause();
      player.removeAttribute("src");
      player.load();
    }
  }

  /** ▶: the chosen answer now, replacing whatever was playing or queued; full reads code and paths too. */
  playNow(id: string, text: string, full = false) {
    if (this.status.isDictating) return;
    this.stop();
    void this.unlockAudio();
    this.push(id, text, full);
  }

  stop() {
    this.generation++;
    this.controller?.abort();
    this.controller = null;
    this.silence();
    this.queue = [];
    this.deferredAnswers.clear();
    this.pendingStep = null;
    this.currentIsStep = false;
    this.notify({ currentId: null, error: "" });
  }

  private push(id: string, text: string, full: boolean) {
    const chunks = speechChunks(forSpeech(text, full));
    if (!chunks.length) return;
    this.handled.add(id);
    this.queue.push({ id: full ? fullReadingId(id) : id, chunks, full });
    void this.processQueue();
  }

  private async synthesize(text: string, full: boolean, signal: AbortSignal) {
    const { voice, speed } = getPreferences();
    const response = await fetch("/v1/audio/speech", {
      method: "POST",
      signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: text, model: "tts-1", voice, speed, response_format: "wav", full }),
    });
    if (!response.ok) throw new Error(`Синтез речи: HTTP ${response.status}`);
    return response.blob();
  }

  /** Loads a part ahead of time: on a weak tablet a fresh src takes a noticeable moment to start. */
  private prepare(audio: HTMLAudioElement, blob: Blob, signal: AbortSignal) {
    signal.throwIfAborted();
    const url = URL.createObjectURL(blob);
    audio.preload = "auto";
    audio.src = url;
    audio.load();
    return url;
  }

  private async play(audio: HTMLAudioElement, signal: AbortSignal) {
    audio.volume = getPreferences().volume;
    await new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        audio.removeEventListener("ended", ended);
        audio.removeEventListener("error", failed);
        signal.removeEventListener("abort", aborted);
      };
      const ended = () => { cleanup(); resolve(); };
      const failed = () => { cleanup(); reject(new Error("Не удалось воспроизвести речь")); };
      const aborted = () => { cleanup(); reject(new DOMException("Остановлено", "AbortError")); };
      audio.addEventListener("ended", ended);
      audio.addEventListener("error", failed);
      signal.addEventListener("abort", aborted, { once: true });
      audio.play().catch((error) => { cleanup(); reject(error); });
    });
  }


  private async processQueue() {
    if (!this.status.isUnlocked || this.status.isDictating || this.status.currentId) return;
    let nextItem: Item | undefined;
    if (this.queue.length) {
      nextItem = this.queue.shift();
      this.currentIsStep = false;
    } else if (this.pendingStep) {
      nextItem = this.pendingStep;
      this.pendingStep = null;
      this.currentIsStep = true;
    }
    if (!nextItem) return;
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const players = [this.audio!, this.spare!];
    const { id, chunks, full = false } = nextItem;
    this.notify({ currentId: id, error: "" });
    const urls = new Set<string>();
    const load = async (index: number) => {
      const url = this.prepare(players[index % 2], await this.synthesize(chunks[index], full, controller.signal), controller.signal);
      urls.add(url);
      return url;
    };
    try {
      let next = load(0);
      for (let index = 0; index < chunks.length; index++) {
        const url = await next;
        if (generation !== this.generation) return;
        // The next part is synthesized and loaded into the other element while this one plays.
        if (index + 1 < chunks.length) {
          next = load(index + 1);
          next.catch(() => {}); // Awaited on the next turn; meanwhile not an unhandled rejection.
        }
        await this.play(players[index % 2], controller.signal);
        URL.revokeObjectURL(url);
        urls.delete(url);
      }
    } catch (error) {
      if (generation !== this.generation) return;
      this.queue = [];
      this.pendingStep = null;
      this.currentIsStep = false;
      // Only a refused play() means the browser wants a new gesture; a failed service does not.
      const refused = error instanceof DOMException && error.name === "NotAllowedError";
      this.notify({ isUnlocked: this.status.isUnlocked && !refused, error: errorMessage(error, "Голосовой сервис") });
    } finally {
      controller.abort(); // A part still being prefetched is not needed any more.
      for (const url of urls) URL.revokeObjectURL(url);
      if (generation === this.generation) {
        for (const player of players) player.removeAttribute("src");
        this.controller = null;
        this.currentIsStep = false;
        this.notify({ currentId: null });
        void this.processQueue();
      }
    }
  }
}

export const audioService = new AudioService();

export function useAudioStatus() {
  return useSyncExternalStore(audioService.subscribe, audioService.getStatus);
}
