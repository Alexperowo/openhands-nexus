import { requestJson } from "./api";
import type { ConversationItem } from "./types";

export async function latestConversationId(signal: AbortSignal) {
  const data = await requestJson<{ items: ConversationItem[] }>("/api/conversations/search?limit=1", { signal });
  if (!Array.isArray(data.items)) throw new Error("Сервер вернул неверный список диалогов");
  return data.items[0]?.id ?? null;
}

// PreToolUse guard: stops commands that break the desktop session or Nexus itself and tells
// the agent the right way instead (nobody confirms actions, Aleksandr's decision). The
// guard path is resolved at build time on this machine, which also runs agent-server.
declare const __NEXUS_GUARD__: string; // vite.config.ts `define`
const guardHooks = {
  pre_tool_use: [{
    matcher: "terminal|file_editor|planning_file_editor",
    hooks: [{ type: "command", command: `/usr/bin/python3 -I '${__NEXUS_GUARD__}'`, timeout: 10 }],
  }],
};

// Canvas keeps its "new chat" start page private, so the host creates the conversation.
export async function createConversation(signal: AbortSignal) {
  const settings = await requestJson<{
    agent_settings?: { llm?: { api_key?: string; base_url?: string }; [key: string]: unknown };
  }>("/api/settings", { signal });
  const agentSettings = settings.agent_settings;
  const llm = agentSettings?.llm;
  if (!agentSettings || !llm) throw new Error("Сначала настройте локальную модель");
  if (!llm.api_key || llm.api_key.includes("*")) {
    const host = new URL(llm.base_url || "http://invalid").hostname;
    if (!["127.0.0.1", "localhost", "[::1]"].includes(host)) {
      throw new Error("Замаскированный ключ внешней модели нельзя восстановить из настроек");
    }
    // Fallback for the local model only, never for an external provider.
    llm.api_key = "not-needed";
  }
  const result = await requestJson<{ id: string }>("/api/conversations", {
    method: "POST", signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_settings: agentSettings, workspace: { working_dir: "/tmp" }, hook_config: guardHooks }),
  });
  if (!result.id) throw new Error("Сервер не вернул ID диалога");
  return result.id;
}
