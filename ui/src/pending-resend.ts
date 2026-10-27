import { useEffect, useRef } from "react";
import type { SocketState } from "./connection-state";
import EventService from "../node_modules/@openhands/agent-canvas/dist/api/event-service/event-service.api.js";
import { useUserConversation } from "../node_modules/@openhands/agent-canvas/dist/hooks/query/use-user-conversation.js";
import { useSendMessage } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-send-message.js";
import { createChatMessage } from "../node_modules/@openhands/agent-canvas/dist/services/chat-service.js";
import { useOptimisticUserMessageStore } from "../node_modules/@openhands/agent-canvas/dist/stores/optimistic-user-message-store.js";
import { isUserMessageEvent } from "../node_modules/@openhands/agent-canvas/dist/types/agent-server/type-guards.js";
import { matchesPendingConversationId } from "../node_modules/@openhands/agent-canvas/dist/utils/pending-task-message-link.js";
import { parseDateAsUTC } from "../node_modules/@openhands/agent-canvas/dist/utils/format-time-delta.js";

// The socket replays missed events right after reopening; wait for that before deciding a message was lost.
const REPLAY_GRACE_MS = 3000;
// History is read from shortly before the oldest lost message: the tablet's clock may differ from the PC's.
export const CLOCK_SLACK_MS = 5 * 60_000;
// A long outage of a busy agent can bury the message under many events; past this, delivery stays unknown.
const HISTORY_PAGES = 10;

type Pending = { id: string; conversationId: string; content: string; status: string; timestamp: string; afterTimestamp?: number; imageUrls: string[]; fileUrls: string[] };
type ServerMessage = { text: string; at: number };

/** Messages written into a socket that died before the server got them: still "sending" after the reconnect replay. */
export function lostPending(pending: Pending[], conversationId: string, reopenedAt: number, server: ServerMessage[]) {
  return pending.filter((message) => matchesPendingConversationId(conversationId, message.conversationId) &&
    message.status === "sending" && Date.parse(message.timestamp) < reopenedAt &&
    !server.some((event) => event.text.trim() === message.content.trim() &&
      (message.afterTimestamp === undefined || event.at > message.afterTimestamp)));
}

/** User messages since the given time. Absence from an incomplete history is not proof of non-delivery:
 *  resending then could run an already accepted task twice, so an incomplete read throws. */
export async function userMessagesSince(conversationId: string, conversation: any, since: number, cancelled: () => boolean) {
  const found: ServerMessage[] = [];
  let pageId: string | undefined;
  for (let pages = 0; pages < HISTORY_PAGES && !cancelled(); pages++) {
    const page = await EventService.searchEvents(conversationId, conversation?.conversation_url ?? null,
      conversation?.session_api_key ?? null,
      { limit: 100, sortOrder: "TIMESTAMP_DESC", timestampGte: new Date(since).toISOString(), pageId, strictPagination: true });
    found.push(...page.items.filter(isUserMessageEvent).map((event: any) => ({
      text: event.llm_message.content.filter((part: any) => part.type === "text").map((part: any) => part.text).join(""),
      at: parseDateAsUTC(event.timestamp).getTime(),
    })));
    if (!page.next_page_id) return found;
    pageId = page.next_page_id;
  }
  throw new Error("Delivery history is incomplete");
}

/** Canvas never resends a message whose WebSocket frame was lost; it shows «Отправка...» until its 150 s timeout. */
export function usePendingResend(conversationId: string | null, state: SocketState) {
  const { data: conversation } = useUserConversation(conversationId);
  const { send } = useSendMessage();
  const outage = useRef({ id: conversationId, wasOpen: false, lost: false });
  if (outage.current.id !== conversationId) outage.current = { id: conversationId, wasOpen: false, lost: false };
  const latest = useRef({ conversation, send });
  latest.current = { conversation, send };

  useEffect(() => {
    const seen = outage.current;
    if (state !== "OPEN") { if (seen.wasOpen) seen.lost = true; return; }
    seen.wasOpen = true;
    if (!seen.lost || !conversationId) return;
    seen.lost = false;
    const reopenedAt = Date.now();
    let cancelled = false;
    // Bind recovery to this conversation; a later render may point latest at another chat.
    const { conversation, send } = latest.current;
    const timer = setTimeout(async () => {
      const store = useOptimisticUserMessageStore.getState();
      const lost = lostPending(store.pendingMessages, conversationId, reopenedAt, []);
      if (!lost.length) return;
      let server: ServerMessage[];
      try {
        const since = Math.min(...lost.map((message) => Date.parse(message.timestamp))) - CLOCK_SLACK_MS;
        server = await userMessagesSince(conversationId, conversation, since, () => cancelled);
        if (cancelled) return;
      } catch {
        if (cancelled) return;
        // Unknown delivery: show the retry button now instead of after the timeout, never risk a duplicate.
        for (const message of lostPending(useOptimisticUserMessageStore.getState().pendingMessages, conversationId, reopenedAt, []))
          store.markPendingMessageError(message.id, "Connection lost");
        return;
      }
      for (const message of lostPending(useOptimisticUserMessageStore.getState().pendingMessages, conversationId, reopenedAt, server)) {
        if (cancelled) return;
        store.markPendingMessageSending(message.id);
        try { await send(createChatMessage(message.content, message.imageUrls, message.fileUrls, message.timestamp)); }
        catch (error) { if (!cancelled) store.markPendingMessageError(message.id, error instanceof Error ? error.message : "Send failed"); }
      }
    }, REPLAY_GRACE_MS);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [conversationId, state]);
}
