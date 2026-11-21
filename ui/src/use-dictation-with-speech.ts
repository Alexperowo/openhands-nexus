import { useEffect, useRef, useState } from "react";
import { readTranscriptionEndpoint } from "../node_modules/@openhands/agent-canvas/dist/utils/transcription-endpoint-storage.js";
import { displayErrorToast } from "../node_modules/@openhands/agent-canvas/dist/utils/custom-toast-handlers.js";
import { audioService } from "./audio-service.ts";
import { DictationSession, type DictationStatus } from "./dictation-session";
import { errorMessage } from "./errors.ts";

type Options = { onTranscript: (text: string) => void };

/** Same Canvas insertion contract, with a bounded request and an explicit cancellation path. */
export function useDictation(options: Options) {
  const latest = useRef(options); latest.current = options;
  const mounted = useRef(true);
  const release = useRef<((readDeferred?: boolean) => void) | null>(null);
  const [status, setStatus] = useState<DictationStatus>("idle");
  const [session] = useState(() => new DictationSession({
    onStatus: value => { if (mounted.current) setStatus(value); },
    onTranscript: text => { if (mounted.current) latest.current.onTranscript(text); },
    onError: error => {
      // Canvas's button replaces every error with the same microphone hint.
      if (mounted.current) displayErrorToast(errorMessage(error, "Сервис распознавания"));
    },
    onEnd: cancelled => { release.current?.(cancelled && mounted.current); release.current = null; },
  }));
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; session.cancel(); release.current?.(); release.current = null; };
  }, [session]);
  const endpoint = readTranscriptionEndpoint();
  const browser = globalThis.window as any;
  const isSupported = endpoint.baseUrl
    ? typeof MediaRecorder !== "undefined" && Boolean(globalThis.navigator?.mediaDevices?.getUserMedia)
    : Boolean(browser?.SpeechRecognition ?? browser?.webkitSpeechRecognition);
  return {
    status, isSupported,
    toggle: () => {
      if (session.status === "idle") {
        if (!isSupported || release.current) return;
        release.current = audioService.beginDictation(session.cancel);
      }
      session.toggle(readTranscriptionEndpoint());
    },
  };
}
