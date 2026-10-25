import type { AgentEvent } from "./speech-events";

/** What llama-swap says about the one loaded model; "busy" is global, not per conversation. */
export type ModelState = "unknown" | "offline" | "loading" | "busy" | "idle";

export interface ActivitySnapshot {
  actions: string[];
  error: string;
}

export type Tone = "work" | "done" | "attention" | "error";

// Instant tools: no observation worth waiting for, never shown as a running step.
const INSTANT = new Set(["think", "finish"]);

// Short Russian names for ConversationErrorEvent; never the raw detail (paths, keys, stack traces).
const ERROR_BY_CODE: Record<string, string> = {
  LLMServiceUnavailableError: "Модель недоступна",
  APIConnectionError: "Модель недоступна",
  LLMTimeoutError: "Модель не ответила вовремя",
  LLMNoResponseError: "Модель не дала ответа",
  LLMContextWindowExceedError: "Диалог не помещается в память модели",
  LLMContextWindowTooSmallError: "Диалог не помещается в память модели",
};
const ERROR_BY_KIND: Record<string, string> = {
  auth: "Модель отклонила ключ доступа",
  quota: "Исчерпан лимит модели",
  rate_limit: "Слишком много запросов к модели",
  config: "Ошибка настроек модели",
  transient: "Временный сбой связи с моделью",
  agent_action: "Сбой действия агента",
  internal: "Внутренняя ошибка агента",
};

const shorten = (text: string, max: number) => (text.length > max ? `${text.slice(0, max - 1)}…` : text);
// Only the last path part: the full path is noise on a magnified screen and may be private.
const fileName = (path: unknown) =>
  typeof path === "string" ? shorten(path.split("/").filter(Boolean).pop() ?? "", 40) : "";
const withName = (label: string, name: string) => (name ? `${label}: ${name}` : label);

/** Neutral label for a tool call; the program name only, never the whole command line. */
export function actionLabel(event: AgentEvent): string {
  const tool = event.tool_name ?? "";
  const action = (event.action ?? {}) as Record<string, unknown>;
  if (tool === "terminal") {
    if (action.is_input) return "Ввод в терминал";
    const program = typeof action.command === "string" ? action.command.trim().split(/\s+/)[0] : "";
    return withName("Выполнение команды", fileName(program));
  }
  if (tool === "file_editor" || tool === "planning_file_editor") {
    const name = fileName(action.path);
    const label = { view: "Чтение файла", create: "Создание файла", undo_edit: "Отмена правки" }[
      String(action.command)] ?? "Изменение файла";
    return withName(label, name);
  }
  if (tool === "apply_patch") return "Изменение файлов";
  if (tool === "glob") return "Поиск файлов";
  if (tool === "grep") return "Поиск в файлах";
  if (tool === "task_tracker") return "Обновление плана задач";
  if (tool === "delegate" || tool === "task") return "Ожидание исполнителя";
  if (tool.startsWith("browser")) return "Работа в браузере";
  return withName("Инструмент", shorten(tool, 30));
}

export function errorLabel(event: { code?: string; classification?: { kind?: string } | null }) {
  return ERROR_BY_CODE[event.code ?? ""] ?? ERROR_BY_KIND[event.classification?.kind ?? ""] ?? "Неизвестный сбой";
}

/**
 * Current run state built from events in server order: tool calls still waiting for their
 * result, and the last conversation error until something shows recovery. Independent of
 * the speech cursor; history found on opening is fed in the same way, silently.
 */
export class AgentActivity {
  private pending = new Map<string, string>();
  private byToolCall = new Map<string, string>();
  private error = "";

  apply(events: AgentEvent[]) {
    for (const event of events) {
      const raw = event as AgentEvent & { action_id?: string; tool_call_id?: string; code?: string };
      if (event.kind === "ActionEvent" && event.source === "agent") {
        this.error = "";
        if (INSTANT.has(event.tool_name ?? "")) continue;
        this.pending.set(event.id, actionLabel(event));
        if (raw.tool_call_id) this.byToolCall.set(raw.tool_call_id, event.id);
      } else if (raw.action_id || (event.kind === "AgentErrorEvent" && raw.tool_call_id)) {
        // ObservationEvent and UserRejectObservation name the action; AgentErrorEvent only the call.
        const id = raw.action_id ?? this.byToolCall.get(raw.tool_call_id ?? "");
        if (id) this.pending.delete(id);
        if (raw.tool_call_id) this.byToolCall.delete(raw.tool_call_id);
      } else if (event.kind === "ConversationErrorEvent") {
        // The run stopped: nothing is executing any more.
        this.error = errorLabel(raw as Parameters<typeof errorLabel>[0]);
        this.pending.clear();
        this.byToolCall.clear();
      } else if (event.kind === "MessageEvent") {
        this.error = "";
      }
    }
  }

  snapshot(): ActivitySnapshot {
    return { actions: [...this.pending.values()], error: this.error };
  }
}

const STATUS_TEXT: Record<string, [string, Tone]> = {
  finished: ["Готово", "done"],
  paused: ["Пауза", "done"],
  stuck: ["Агент застрял, нужна помощь", "attention"],
  awaiting_user_input: ["Агент ждёт вашего ответа", "attention"],
};

/**
 * One line from what is actually known. A stage is named only when an event or the model
 * health proves it; otherwise the wording says what is likely, never more.
 */
export function describeStatus(status: string, activity: ActivitySnapshot, model: ModelState):
  { text: string; tone: Tone } | null {
  const [first] = activity.actions;
  if (status === "awaiting_user_confirmation") {
    return { text: withName("Нужно ваше подтверждение", first ?? ""), tone: "attention" };
  }
  if (status === "error") return { text: activity.error ? `Ошибка: ${activity.error}` : "Ошибка агента", tone: "error" };
  if (status in STATUS_TEXT) {
    const [text, tone] = STATUS_TEXT[status];
    return { text, tone };
  }
  if (status !== "running") return null;
  if (model === "offline") return { text: "Агент ждёт модель", tone: "error" };
  if (model === "loading") return { text: "Модель загружается", tone: "work" };
  if (activity.error) return { text: `${activity.error}. Возможна повторная попытка`, tone: "error" };
  if (activity.actions.length > 1) return { text: `${first} и ещё ${activity.actions.length - 1}`, tone: "work" };
  if (first) return { text: first, tone: "work" };
  if (model === "busy") return { text: "Модель генерирует ответ", tone: "work" };
  if (model === "idle") return { text: "Агент работает: вероятно, модель читает контекст", tone: "work" };
  return { text: "Агент работает", tone: "work" };
}

/**
 * Reads llama-swap through the gateway: /llm/running names the loaded model and its state,
 * that model's own /health tells whether it generates. An unreachable gateway is "unknown"
 * (the page itself is offline), not a model fault.
 */
export async function readModelState(signal: AbortSignal): Promise<ModelState> {
  const options = { signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) };
  let response: Response;
  try {
    response = await fetch("/llm/running", options);
  } catch {
    return "unknown";
  }
  // The proxy answers 502/500/504 itself when llama-swap is not running.
  if ([500, 502, 504].includes(response.status)) return "offline";
  if (!response.ok) return "unknown";
  const running: unknown = (await response.json().catch(() => ({})))?.running;
  if (!Array.isArray(running)) return "unknown";
  // A swap stops the old model, then starts the chosen one.
  if (running.some(item => item?.state === "starting" || item?.state === "stopping")) return "loading";
  const ready = running.find(item => item?.state === "ready");
  // Nothing loaded: llama-swap starts the model on the next request.
  if (typeof ready?.model !== "string") return "idle";
  const health = await fetch(`/llm/model/${encodeURIComponent(ready.model)}/health`, options)
    .then(answer => (answer.ok ? answer.json() : {}))
    .catch(() => ({}));
  return Number(health?.slots_processing) > 0 ? "busy" : "idle";
}
