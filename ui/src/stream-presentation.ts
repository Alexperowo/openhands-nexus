import { getReasoningContent, splitInlineThink } from "../node_modules/@openhands/agent-canvas/dist/components/conversation-events/chat/event-thought-helpers.js";

type ReasoningSource = Parameters<typeof getReasoningContent>[0];
export interface AnswerSource extends ReasoningSource {
  kind: string;
  content?: string | null;
  llm_message?: ReasoningSource & { content?: string | Array<{type: string; text?: string; image_urls?: string[]}> };
  action?: {message?: string; args?: {message?: string}};
}

export function streamedText(event: ReasoningSource & { content?: string | null }) {
  const inline = splitInlineThink(event.content ?? "", { streaming: true });
  return {
    reasoning: [getReasoningContent(event), inline.reasoning].filter(Boolean).join("\n\n"),
    message: inline.message,
  };
}

export function answerPresentation(event: AnswerSource) {
  if (event.kind === "StreamingDeltaEvent") return streamedText(event);
  const content = event.llm_message?.content;
  const text = event.kind === "MessageEvent" ? (typeof content === "string" ? content : (content ?? [])
    .filter(part => part.type === "text").map(part => part.text ?? "").join("\n")) :
    event.action?.message ?? event.action?.args?.message ?? "";
  const inline = splitInlineThink(text);
  return { message: inline.message,
    reasoning: [getReasoningContent(event.llm_message ?? event), inline.reasoning].filter(Boolean).join("\n\n") };
}

export interface ContextUsage { perTurnToken: number; contextWindow: number }
export interface ContextReading { id: string | null; usage: ContextUsage | null; stale: boolean }

export function retainContext(previous: ContextReading, id: string | null, incoming: ContextUsage | null): ContextReading {
  // The first render of a new route can still see the previous conversation's store.
  if (previous.id !== id) return { id, usage: null, stale: false };
  if (incoming && Number.isFinite(incoming.contextWindow) && incoming.contextWindow > 0 &&
      Number.isFinite(incoming.perTurnToken) && incoming.perTurnToken >= 0) {
    return { id, usage: incoming, stale: false };
  }
  return { ...previous, stale: previous.usage !== null };
}
