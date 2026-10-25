// agent-server 1.58 (still in 1.58.2 and main) adds LLMs to the usage stats only when the agent
// starts with the first message, so a model switched in before that is never counted and the
// context meter stays empty. Until the agent has started a conversation holds nothing, so the
// host starts a new one with the chosen model instead of switching.
import { createConversation, isLocalModel } from "./conversations.ts";
import { requestJson } from "./api.ts";

/** Window event with {from, to}: App opens the replacement and drops the empty conversation. */
export const REPLACED_EVENT = "nexus:conversation-replaced";

const SWITCH_PATH = /^\/api\/conversations\/([^/]+)\/switch_llm$/;

export type EarlySwitch = { conversationId: string; profile: string; llm: Record<string, unknown> };

/** A Canvas profile switch to a local model; null for anything else, which goes on unchanged. */
export function profileSwitch(url: string, method: string | undefined, body: unknown, origin: string): EarlySwitch | null {
  if ((method ?? "GET").toUpperCase() !== "POST" || typeof body !== "string") return null;
  const match = SWITCH_PATH.exec(new URL(url, origin).pathname);
  if (!match) return null;
  let llm: Record<string, unknown> | undefined;
  try {
    llm = JSON.parse(body)?.llm;
  } catch {
    return null;
  }
  const profile = /^profile:(.+):[^:]+$/.exec(String(llm?.usage_id ?? ""))?.[1];
  if (!llm || !profile || !isLocalModel(llm.base_url)) return null;
  // The key arrives encrypted for this switch; the local model needs none.
  const { api_key: _key, ...model } = llm;
  return { conversationId: decodeURIComponent(match[1]), profile, llm: model };
}

const hasEvent = async (conversationId: string, kind: string) => {
  const found = await requestJson<{ items?: unknown[] }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/events/search?kind=${kind}&limit=1`);
  if (!Array.isArray(found.items)) throw new Error("Сервер вернул неверный список событий");
  return found.items.length > 0;
};

/** The agent writes its system prompt when it starts; no messages can exist before that. */
export const agentStarted = (conversationId: string) => hasEvent(conversationId, "SystemPromptEvent");
export const hasMessages = (conversationId: string) => hasEvent(conversationId, "MessageEvent");

/** Wraps window.fetch; `onReplaced` gets the empty conversation, its replacement and the profile. */
export function installEarlySwitch(onReplaced: (from: string, to: string, profile: string) => void) {
  const next = window.fetch;
  window.fetch = (input, init) => {
    const early = typeof input === "string" || input instanceof URL
      ? profileSwitch(String(input), init?.method, init?.body, window.location.origin) : null;
    if (!early) return next(input, init);
    return (async () => {
      try {
        if (!(await agentStarted(early.conversationId))) {
          const id = await createConversation(AbortSignal.timeout(15000), early.llm);
          onReplaced(early.conversationId, id, early.profile);
          return new Response(JSON.stringify({ success: true }), { headers: { "Content-Type": "application/json" } });
        }
      } catch (error) {
        // An ordinary switch still works; only the meter misses this model.
        console.warn("[model-switch] new conversation failed, switching in place", error);
      }
      return next(input, init);
    })();
  };
}
