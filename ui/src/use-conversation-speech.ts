import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { audioService } from "./audio-service.ts";
import { getPreferences } from "./preferences.ts";
import { requestJson, errorMessage } from "./api.ts";
import { SpeechEvents, type AgentEvent } from "./speech-events.ts";
import { SessionEvents, openingCursor, type SessionFrame } from "./session-events.ts";
import { AgentActivity, CheckedSpeech, ModelProgress, readModelState, type ActivitySnapshot, type ModelState } from "./agent-activity.ts";

const NO_ACTIVITY: ActivitySnapshot = { actions: [], error: "" };
const CONNECTION_LOST = "Нет связи с сервером";
const MODEL_INTERVAL = 1500;
const RETRY_FIRST = 500;
const RETRY_MAX = 10000;
const CHECK_INTERVAL = 30000;
const RECHECK_DELAY = 3000;

export interface SpeechSnapshot {
  status: string; error: string; ready: boolean; id: string | null;
  activity: ActivitySnapshot; model: ModelState;
}
export function snapshotForConversation(state: SpeechSnapshot, id: string | null): SpeechSnapshot {
  return state.id === id ? state : {id, status: "", error: "", ready: false, activity: NO_ACTIVITY, model: "unknown"};
}
export function mergeSpeechSnapshot(previous: SpeechSnapshot, patch: Partial<SpeechSnapshot>): SpeechSnapshot {
  const next = { ...previous, ...patch };
  const sameActivity = previous.activity.error === next.activity.error &&
    previous.activity.missing === next.activity.missing &&
    previous.activity.actions.length === next.activity.actions.length &&
    previous.activity.actions.every((action, index) => action === next.activity.actions[index]);
  if (sameActivity) next.activity = previous.activity;
  return (Object.keys(next) as (keyof SpeechSnapshot)[]).every(key => next[key] === previous[key]) ? previous : next;
}

export function useConversationSpeech(conversationId: string | null) {
  const [state, setState] = useState<SpeechSnapshot>({
    status: "", error: "", ready: false, id: conversationId,
    activity: NO_ACTIVITY, model: "unknown" as ModelState,
  });
  const activeRequest = useRef<AbortController | null>(null);
  const cancel = useCallback(() => {
    activeRequest.current?.abort();
    audioService.stop();
  }, []);

  useLayoutEffect(() => {
    setState({ status: "", error: "", ready: false, id: conversationId, activity: NO_ACTIVITY, model: "unknown" });
    audioService.stop();
    if (!conversationId) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    const { signal } = controller;
    const speech = new SpeechEvents();
    const activity = new AgentActivity();
    const checked = new CheckedSpeech(activity);
    const path = `/api/conversations/${encodeURIComponent(conversationId)}`;
    let session: SessionEvents | null = null;
    let socket: WebSocket | null = null;
    let failures = 0;
    let behind = 0;
    let model: ModelState = "unknown";
    let modelAt = 0;
    const progress = new ModelProgress();
    let modelTimer: ReturnType<typeof setTimeout> | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let checkTimer: ReturnType<typeof setTimeout> | undefined;
    const visible = () => document.visibilityState === "visible";

    // Model health matters only while the agent works and someone can see it.
    const modelWanted = () => Boolean(session?.statusKnown) && visible() &&
      activity.verifiedStatus(session!.status) === "running";
    const readModel = async () => {
      if (!modelWanted()) { modelTimer = undefined; return; }
      const reading = await readModelState(signal);
      modelTimer = undefined;
      if (signal.aborted) return;
      model = progress.update(reading, Date.now());
      modelAt = Date.now();
      publish();
    };
    const publish = () => {
      if (!session?.statusKnown || signal.aborted) return;
      if (!modelWanted()) {
        model = "unknown";
        modelAt = 0;
        progress.reset();
      } else if (modelTimer === undefined) {
        modelTimer = setTimeout(readModel, modelAt ? MODEL_INTERVAL : 0);
      }
      setState(previous => mergeSpeechSnapshot(previous, {
        status: activity.verifiedStatus(session!.status), error: "", ready: true, id: conversationId,
        activity: activity.snapshot(), model,
      }));
    };

    const speak = (event: AgentEvent) => {
      const said = checked.take(event, speech.takeText(event));
      if (said.length && getPreferences().autoSpeak) {
        for (const [id, text] of said) audioService.speak(id, text);
      } else {
        const step = speech.takeStep(event);
        if (step && getPreferences().autoSpeak && getPreferences().speakSteps) {
          audioService.speakStep(event.id, step);
        }
      }
    };
    const receive = (frame: SessionFrame) => {
      const taken = session!.take(frame);
      if (taken?.fresh) {
        progress.settle();
        activity.apply([taken.event]);
        speak(taken.event);
      } else if (taken) {
        speech.seedHistory([taken.event]);
        activity.apply([taken.event]);
      }
      publish();
    };

    const fail = (error: unknown) => {
      if (signal.aborted) return;
      failures += 1;
      // One quick reconnect after a dropped socket is not worth a notice; a failed attempt is.
      if (error || failures > 1) {
        setState(previous => mergeSpeechSnapshot(previous, { error: error ? errorMessage(error) : CONNECTION_LOST }));
      }
      retryTimer = setTimeout(connect, Math.min(RETRY_FIRST * 2 ** (failures - 1), RETRY_MAX));
    };
    const connect = async () => {
      retryTimer = undefined;
      if (!session) {
        try {
          session = new SessionEvents(openingCursor(await requestJson<number>(`${path}/events/count`, { signal })));
        } catch (error) {
          fail(error);
          return;
        }
      }
      if (signal.aborted) return;
      // The gateway adds the session key to /sockets, as to /api.
      const url = new URL(`/sockets/session/${encodeURIComponent(conversationId)}`, location.href);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.searchParams.set("after_seq", String(session.lastSeq));
      const ws = new WebSocket(url);
      socket = ws;
      let synced = false;
      ws.onmessage = ({ data }) => {
        if (socket !== ws || signal.aborted) return;
        let frame: SessionFrame;
        try {
          frame = JSON.parse(String(data));
        } catch {
          return;
        }
        if (frame?.type === "sync") { synced = true; failures = 0; }
        receive(frame);
      };
      ws.onclose = () => {
        if (socket !== ws) return;
        socket = null;
        fail(synced ? null : new Error(CONNECTION_LOST));
      };
    };
    // A socket can die silently (Wi-Fi drop without a close); the log length shows it fell behind.
    const check = async () => {
      checkTimer = setTimeout(check, CHECK_INTERVAL);
      const ws = socket;
      if (!session || !ws || ws.readyState !== WebSocket.OPEN) return;
      let count: number;
      try {
        count = await requestJson<number>(`${path}/events/count`, { signal });
      } catch {
        return;
      }
      if (socket !== ws || count - 1 <= session.lastSeq) { behind = 0; return; }
      // Once may be an event still on its way; the second time the socket is replaced.
      if (++behind === 1) {
        clearTimeout(checkTimer);
        checkTimer = setTimeout(check, RECHECK_DELAY);
        return;
      }
      behind = 0;
      socket = null;
      ws.close();
      void connect();
    };
    // A locked screen may freeze the page and drop the socket; on return it reconnects at once.
    const resume = () => {
      if (!visible() || signal.aborted) return;
      if (!socket && retryTimer !== undefined) {
        clearTimeout(retryTimer);
        void connect();
      }
      clearTimeout(checkTimer);
      void check();
      publish();
    };
    signal.addEventListener("abort", () => {
      [modelTimer, retryTimer, checkTimer].forEach(clearTimeout);
      const ws = socket;
      socket = null;
      ws?.close();
    });
    document.addEventListener("visibilitychange", resume);
    void connect();
    checkTimer = setTimeout(check, CHECK_INTERVAL);
    return () => {
      controller.abort();
      document.removeEventListener("visibilitychange", resume);
      audioService.stop();
    };
  }, [conversationId]);

  // A new route must not announce the preceding conversation's error/status before effect cleanup.
  return { ...snapshotForConversation(state, conversationId), cancel };
}
