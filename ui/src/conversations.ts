import { requestJson } from "./api.ts";
import type { ConversationItem } from "./types.ts";

export async function latestConversationId(signal: AbortSignal) {
  const data = await requestJson<{ items: ConversationItem[] }>("/api/conversations/search?limit=1", { signal });
  if (!Array.isArray(data.items)) throw new Error("Сервер вернул неверный список диалогов");
  return data.items[0]?.id ?? null;
}

type LlmConfig = { api_key?: string; base_url?: string; [key: string]: unknown };

export const isLocalModel = (baseUrl: unknown) => {
  try {
    return ["127.0.0.1", "localhost", "[::1]"].includes(new URL(String(baseUrl || "http://invalid")).hostname);
  } catch {
    return false;
  }
};

// Canvas keeps its "new chat" start page private, so the host creates the conversation;
// installGuardFetch (init.ts) adds the guard hook to it like to every other start.
// `model` replaces the default model (a profile chosen before the first message).
export async function createConversation(signal: AbortSignal, model?: LlmConfig) {
  const settings = await requestJson<{
    agent_settings?: { llm?: LlmConfig; [key: string]: unknown };
  }>("/api/settings", { signal });
  const agentSettings = settings.agent_settings;
  const llm = model ?? agentSettings?.llm;
  if (!agentSettings || !llm) throw new Error("Сначала настройте локальную модель");
  agentSettings.llm = llm;
  if (!llm.api_key || llm.api_key.includes("*")) {
    if (!isLocalModel(llm.base_url)) {
      throw new Error("Замаскированный ключ внешней модели нельзя восстановить из настроек");
    }
    // Fallback for the local model only, never for an external provider.
    llm.api_key = "not-needed";
  }
  const result = await requestJson<{ id: string }>("/api/conversations", {
    method: "POST", signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_settings: agentSettings, workspace: { working_dir: "/tmp" } }),
  });
  if (!result.id) throw new Error("Сервер не вернул ID диалога");
  return result.id;
}
