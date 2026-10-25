import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { audioService } from "./audio-service.ts";
import { getPreferences } from "./preferences.ts";
import { requestJson, errorMessage } from "./api.ts";
import { SpeechEvents, type EventPage } from "./speech-events.ts";
import { AgentActivity, readModelState, type ActivitySnapshot, type ModelState } from "./agent-activity.ts";

const NO_ACTIVITY: ActivitySnapshot = { actions: [], error: "" };

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
    const events = new SpeechEvents();
    const activity = new AgentActivity();
    const path = `/api/conversations/${encodeURIComponent(conversationId)}`;
    let timer: ReturnType<typeof setTimeout>;
    let polling = false;

    const poll = async () => {
      polling = true;
      try {
        const newEvents = await events.readNew(async (pageId, limit) => {
          const query = new URLSearchParams({ sort_order: "TIMESTAMP_DESC", limit: String(limit) });
          if (pageId) query.set("page_id", pageId);
          const page = await requestJson<EventPage>(`${path}/events/search?${query}`, { signal });
          signal.throwIfAborted();
          if (!Array.isArray(page.items) || page.items.some((event) => typeof event?.id !== "string" || !event.id)) {
            throw new Error("Сервер вернул неверный список событий");
          }
          return page;
        }, (history) => activity.apply(history));
        activity.apply(newEvents);
        if (signal.aborted) return;
        for (const event of newEvents) {
          const text = events.takeText(event);
          if (text && getPreferences().autoSpeak) {
            audioService.speak(event.id, text);
          } else {
            const step = events.takeStep(event);
            if (step && getPreferences().autoSpeak && getPreferences().speakSteps) {
              audioService.speakStep(event.id, step);
            }
          }
        }
        const [conversation, model] = await Promise.all([
          requestJson<{ execution_status: string }>(path, { signal }),
          readModelState(signal),
        ]);
        if (signal.aborted) return;
        setState(previous => mergeSpeechSnapshot(previous, {
          status: conversation.execution_status, error: "", ready: true, id: conversationId,
          activity: activity.snapshot(), model,
        }));
      } catch (error) {
        if (!signal.aborted) setState(previous => mergeSpeechSnapshot(previous, { error: errorMessage(error) }));
      } finally {
        polling = false;
        // Schedule after completion: slow requests never overlap.
        if (!signal.aborted) timer = setTimeout(poll, 1500);
      }
    };
    // A hidden page (screen locked) gets its timers throttled, a frozen one none at all;
    // on return the poll runs at once, so an answer that came meanwhile is read then.
    const resume = () => {
      if (document.visibilityState !== "visible" || polling || signal.aborted) return;
      clearTimeout(timer);
      void poll();
    };
    document.addEventListener("visibilitychange", resume);
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      audioService.stop();
    };
  }, [conversationId]);

  // A new route must not announce the preceding conversation's error/status before effect cleanup.
  return { ...snapshotForConversation(state, conversationId), cancel };
}
