// Reasoning level of the local models, sent with every request: the loaded model stays as it
// is and a new level applies from the agent's next step. Tess and Holo templates read
// enable_thinking and reasoning_effort (low, medium, xhigh; low and xhigh add a line to the
// system prompt, so moving between efforts makes the server read the context once again);
// the Nex template reads only reasoning_effort, by its card "none", "medium" (adaptive, the
// model decides whether to think) and "high" (always thinks), so the levels map onto those.
// llama-server ends thinking after thinking_budget_tokens, so a model that loops in its
// reasoning still gets to act. High matches the defaults in agent/config/profiles.json.
import { isLocalModel } from "./conversations.ts";
import { requestJson } from "./api.ts";

export type ReasoningLevel = "off" | "minimal" | "low" | "medium" | "high" | "max";

export const REASONING: Record<ReasoningLevel, { label: string; thinking: boolean; effort: string; budget: number }> = {
  off: { label: "Выкл", thinking: false, effort: "none", budget: 0 },
  minimal: { label: "Минимум", thinking: true, effort: "low", budget: 512 },
  low: { label: "Низкое", thinking: true, effort: "low", budget: 2048 },
  medium: { label: "Среднее", thinking: true, effort: "medium", budget: 4096 },
  high: { label: "Высокое", thinking: true, effort: "xhigh", budget: 8192 },
  max: { label: "Максимум", thinking: true, effort: "xhigh", budget: 16384 },
};

export const REASONING_LEVELS = Object.keys(REASONING) as ReasoningLevel[];

type Llm = Record<string, unknown>;
const record = (value: unknown) => (value && typeof value === "object" ? value as Record<string, unknown> : {});

const NEX_EFFORT: Record<string, string> = { none: "none", low: "medium", medium: "medium", xhigh: "high" };
/** The effort as the model's template names it. */
const effortFor = (llm: Llm, effort: string) => (/(^|\/)nex/i.test(String(llm.model ?? "")) ? NEX_EFFORT[effort] : effort);

/** The model with this level; an external provider is returned unchanged. */
export function withReasoning<T extends Llm>(llm: T, level: ReasoningLevel): T {
  if (!isLocalModel(llm.base_url)) return llm;
  const { thinking, effort, budget } = REASONING[level];
  const extra = record(llm.litellm_extra_body);
  return {
    ...llm,
    litellm_extra_body: {
      ...extra,
      chat_template_kwargs: { ...record(extra.chat_template_kwargs), enable_thinking: thinking, reasoning_effort: effortFor(llm, effort) },
      thinking_budget_tokens: budget,
    },
  };
}

/** The level the model runs with; null for settings no level describes (e.g. no budget). */
export function reasoningOf(llm: unknown): ReasoningLevel | null {
  const extra = record(record(llm).litellm_extra_body);
  const kwargs = record(extra.chat_template_kwargs);
  return REASONING_LEVELS.find((level) => {
    const { thinking, effort, budget } = REASONING[level];
    return kwargs.enable_thinking === thinking && kwargs.reasoning_effort === effortFor(record(llm), effort)
      && extra.thinking_budget_tokens === budget;
  }) ?? null;
}

const START_PATH = "/api/conversations";
const SWITCH_PATH = /^\/api\/conversations\/([^/]+)\/switch_llm$/;

/** Window event with {conversationId}: its model was switched, the level may differ. */
export const REASONING_CHANGED_EVENT = "nexus:reasoning-changed";

/** A conversation start or model switch with the level applied; other requests are unchanged. */
export function reasonedBody(url: string, method: string | undefined, body: unknown, origin: string, level: ReasoningLevel) {
  if ((method ?? "GET").toUpperCase() !== "POST" || typeof body !== "string") return body;
  const path = new URL(url, origin).pathname;
  const start = path === START_PATH;
  if (!start && !SWITCH_PATH.test(path)) return body;
  let payload: Record<string, unknown>;
  try {
    payload = record(JSON.parse(body));
  } catch {
    return body;
  }
  if (start) {
    const settings = record(payload.agent_settings);
    if (!payload.agent_settings || !settings.llm) return body;
    return JSON.stringify({ ...payload, agent_settings: { ...settings, llm: withReasoning(record(settings.llm), level) } });
  }
  if (!payload.llm) return body;
  return JSON.stringify({ ...payload, llm: withReasoning(record(payload.llm), level) });
}

/** Every start and switch gets the current level, whichever part of Canvas sends it. */
export function installReasoningFetch(currentLevel: () => ReasoningLevel) {
  const next = window.fetch;
  window.fetch = (input, init) => {
    if (typeof input !== "string" && !(input instanceof URL)) return next(input, init);
    const body = reasonedBody(String(input), init?.method, init?.body, window.location.origin, currentLevel());
    const response = next(input, body === init?.body ? init : { ...init, body: body as BodyInit });
    // Any switch may change the level, even one whose body already had it.
    const switched = (init?.method ?? "GET").toUpperCase() === "POST"
      && SWITCH_PATH.exec(new URL(String(input), window.location.origin).pathname);
    if (!switched) return response;
    return response.then((result) => {
      if (result.ok) {
        const conversationId = decodeURIComponent(switched[1]);
        window.dispatchEvent(new CustomEvent(REASONING_CHANGED_EVENT, { detail: { conversationId } }));
      }
      return result;
    });
  };
}

const newUsageId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;

/**
 * Switches the conversation to its own profile again, so the fetch wrapper adds the current
 * level; before the first message model-switch.ts opens a new conversation instead.
 */
export async function switchReasoning(conversationId: string, profile: string) {
  const { config } = await requestJson<{ config?: Llm }>(`/api/profiles/${encodeURIComponent(profile)}`);
  if (!config || !isLocalModel(config.base_url)) throw new Error("Уровень рассуждений задаётся только локальной модели");
  await requestJson(`/api/conversations/${encodeURIComponent(conversationId)}/switch_llm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Canvas names a profile switch the same way; the local model needs no key.
    body: JSON.stringify({ llm: { ...config, api_key: "not-needed", usage_id: `profile:${profile}:${newUsageId()}` } }),
  });
}
