import type { AgentEvent } from "./speech-events";

/**
 * What llama-swap says about the one loaded model; global, not per conversation. ik_llama counts
 * a slot as busy only once it writes: while it reads the prompt the slot is idle, and only its
 * KV-cache tokens (metrics) grow.
 */
export type ModelReading = { state: "unknown" | "offline" | "loading" | "busy" | "idle"; tokens?: number; silent?: boolean };
/** With metrics, a request in flight is "reading" or "writing", and "stalled" when it stops moving. */
export type ModelState = ModelReading["state"] | "reading" | "writing" | "stalled";

export const MODEL_STALLED = "Модель не продвигается больше 2 минут — возможно, зависла";
// One batch of a long context takes seconds (2048 tokens of 45k in 1.5 s, 27.10); images as well.
export const STALL_MS = 120_000;

export interface ActivitySnapshot {
  actions: string[];
  error: string;
  /** What the goal check found missing, when it stopped without confirming the result. */
  missing?: string;
}

// The server's goal loop (agent/sdk-patch/nexus_goal.py): its own messages and the judge's
// marker for a step only the owner can take.
export const FOLLOWUP_MARK = "Проверка Nexus:";
export const NEEDS_USER = "Нужно ваше решение: ";
// worked: the agent acted since the loop's last update, so a finish now waits for the judge.
// request: the loop just started, so the next user message is its request (the owner's words,
// which differ from the goal as the server understood it).
interface Goal { status: string; missing: string; worked: boolean; request: boolean }
const NO_GOAL: Goal = { status: "", missing: "", worked: false, request: false };

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

const messageText = (event: AgentEvent) =>
  (event.llm_message?.content ?? []).filter((part) => part.type === "text").map((part) => part.text ?? "").join("").trim();

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
  private goal = NO_GOAL;
  // The agent did something since the owner's last message: a plain reply has no result to check.
  private acted = false;

  apply(events: AgentEvent[]) {
    for (const event of events) {
      const raw = event as AgentEvent & { action_id?: string; tool_call_id?: string; code?: string; key?: string; value?: any };
      if (event.source === "agent") this.goal = { ...this.goal, worked: true };
      if (event.kind === "ActionEvent" && event.source === "agent") {
        this.error = "";
        if (INSTANT.has(event.tool_name ?? "")) continue;
        this.acted = true;
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
      } else if (event.kind === "ConversationStateUpdateEvent" && raw.key === "goal") {
        this.goal = { status: String(raw.value?.status ?? ""), missing: String(raw.value?.verdict?.missing ?? ""), worked: false,
          request: Boolean(raw.value?.active) && !raw.value?.verdict };
      } else if (event.kind === "MessageEvent") {
        this.error = "";
        // A request outside the loop (talk, a message while the agent worked, files) is not checked.
        const text = event.source === "user" ? messageText(event) : "";
        if (!text || text.startsWith(FOLLOWUP_MARK)) continue;
        this.acted = false;
        this.goal = this.goal.request ? { ...this.goal, request: false } : NO_GOAL;
      }
    }
  }

  snapshot(): ActivitySnapshot {
    const missing = this.goal.status === "capped" ? this.goal.missing : "";
    return { actions: [...this.pending.values()], error: this.error, ...(missing ? { missing } : {}) };
  }

  /** The goal check still runs: the agent's answer may not be the last word. */
  goalRunning(): boolean { return this.goal.status === "running"; }

  /** For the voice: the check's word on a finished goal it did not confirm, else "". */
  verdictSpeech(): string {
    const status = this.verifiedStatus("finished");
    return status === "needs_user" || status === "unconfirmed" ? describeStatus(status, this.snapshot(), "unknown")!.text : "";
  }

  /** The execution status with the goal check folded in: a finish says whether it was confirmed. */
  verifiedStatus(status: string): string {
    if (this.goal.status === "running") {
      // Before the agent's first step the finish is the previous run's.
      if (status === "finished") return this.goal.worked ? "checking" : "running";
      return status === "idle" ? "running" : status;
    }
    if (status !== "finished") return status;
    if (this.goal.status === "complete") return "verified";
    if (this.goal.status === "capped") return this.goal.missing.startsWith(NEEDS_USER) ? "needs_user" : "unconfirmed";
    // A reply in words (no goal, no action) is just an answer: no «not checked» for it.
    return this.goal.status || this.acted ? "unverified" : status;
  }
}

/**
 * The voice agrees with the goal check: while a goal is checked, the agent's answer waits for the
 * verdict. Confirmed: the answer. Not confirmed: the answer, then what is missing. Another round
 * (the check's follow-up): that answer is dropped, the next one waits. An error releases it.
 * Only fresh events come here, so a goal already running when the page opened counts from its
 * first fresh event.
 */
export class CheckedSpeech {
  private held: [string, string] | null = null;
  private running = false;
  private activity: AgentActivity;
  constructor(activity: AgentActivity) { this.activity = activity; }

  /** Called after activity.apply(event) with the event's spoken text; returns [id, text] to say now. */
  take(event: AgentEvent, text: string): [string, string][] {
    if (event.source === "user" && event.kind === "MessageEvent") this.held = null;
    const failed = event.kind === "ConversationErrorEvent";
    const running = this.activity.goalRunning(), ended = this.running && !running;
    this.running = running;
    if (text && running && !failed) { this.held = [event.id, text]; return []; }
    const said: [string, string][] = text ? [[event.id, text]] : [];
    if (this.held && (failed || ended)) { said.unshift(this.held); this.held = null; }
    const verdict = ended ? this.activity.verdictSpeech() : "";
    if (verdict) said.push([event.id, verdict]);
    return said;
  }
}

const STATUS_TEXT: Record<string, [string, Tone]> = {
  checking: ["Проверяю результат", "work"],
  verified: ["Готово, проверено", "done"],
  unverified: ["Закончил, результат не проверен", "done"],
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
  if (status === "needs_user") return { text: shorten(activity.missing ?? NEEDS_USER, 160), tone: "attention" };
  if (status === "unconfirmed") {
    return { text: `Закончил, но не всё подтверждено: ${shorten(activity.missing ?? "", 120)}`, tone: "attention" };
  }
  if (status in STATUS_TEXT) {
    const [text, tone] = STATUS_TEXT[status];
    return { text, tone };
  }
  if (status !== "running") return null;
  if (model === "offline") return { text: "Агент ждёт модель", tone: "error" };
  if (model === "loading") return { text: "Модель загружается", tone: "work" };
  if (model === "stalled") return { text: MODEL_STALLED, tone: "attention" };
  if (activity.error) return { text: `${activity.error}. Возможна повторная попытка`, tone: "error" };
  if (activity.actions.length > 1) return { text: `${first} и ещё ${activity.actions.length - 1}`, tone: "work" };
  if (first) return { text: first, tone: "work" };
  if (model === "reading") return { text: "Модель читает контекст", tone: "work" };
  if (model === "writing" || model === "busy") return { text: "Модель пишет ответ", tone: "work" };
  // Without metrics the reading of a prompt looks idle too.
  if (model === "idle") return { text: "Агент работает: вероятно, модель читает контекст", tone: "work" };
  return { text: "Агент работает", tone: "work" };
}

/**
 * The stage of the model's request from readings 1.5 s apart: KV-cache tokens growing on an idle
 * slot mean the prompt is being read, a busy slot that it writes. Without metrics (a server
 * without --metrics) the reading is passed on as is: no progress is claimed and no stall either.
 */
export class ModelProgress {
  private tokens?: number;
  private since = 0;
  private stage?: "reading" | "writing";

  reset() {
    this.tokens = this.stage = undefined;
  }

  /** The agent got an answer (an event came): the model's request is over until the cache moves. */
  settle() {
    this.stage = undefined;
  }

  update(reading: ModelReading, now: number): ModelState {
    if (reading.state !== "busy" && reading.state !== "idle") {
      this.reset();
      return reading.state;
    }
    if (reading.silent) {
      // Metrics wait for the current batch: a long one or a hung server, a request either way.
      if (!this.stage) [this.stage, this.since] = ["reading", now];
    } else if (reading.tokens === undefined) {
      return reading.state;
    } else {
      // Fewer tokens: a new request kept only the shared start of the cache.
      const moved = this.tokens !== undefined && reading.tokens !== this.tokens;
      this.tokens = reading.tokens;
      if (reading.state === "busy" ? moved || this.stage !== "writing" : moved) {
        [this.stage, this.since] = [reading.state === "busy" ? "writing" : "reading", now];
      } else if (reading.state === "idle" && this.stage !== "reading") {
        this.stage = undefined;
        return "idle";
      }
    }
    return now - this.since >= STALL_MS ? "stalled" : this.stage ?? reading.state;
  }
}

const metric = (text: string, name: string) => {
  const value = Number(text.match(new RegExp(`^llamacpp:${name}\\s+(\\S+)`, "m"))?.[1]);
  return Number.isFinite(value) ? value : undefined;
};

/**
 * Reads llama-swap through the gateway: /llm/running names the loaded model and its state,
 * that model's own /metrics whether it works and how far (KV-cache tokens), /health whether
 * it works when the server has no metrics. An unreachable gateway is "unknown" (the page
 * itself is offline), not a model fault.
 */
export async function readModelState(signal: AbortSignal): Promise<ModelReading> {
  const options = { signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) };
  let response: Response;
  try {
    response = await fetch("/llm/running", options);
  } catch {
    return { state: "unknown" };
  }
  // The proxy answers 502/500/504 itself when llama-swap is not running.
  if ([500, 502, 504].includes(response.status)) return { state: "offline" };
  if (!response.ok) return { state: "unknown" };
  const running: unknown = (await response.json().catch(() => ({})))?.running;
  if (!Array.isArray(running)) return { state: "unknown" };
  // A swap stops the old model, then starts the chosen one.
  if (running.some(item => item?.state === "starting" || item?.state === "stopping")) return { state: "loading" };
  const ready = running.find(item => item?.state === "ready");
  // Nothing loaded: llama-swap starts the model on the next request.
  if (typeof ready?.model !== "string") return { state: "idle" };
  const model = `/llm/model/${encodeURIComponent(ready.model)}`;
  // llama-server answers both between batches of its work: a long batch delays the answer,
  // a hung server never gives it. Silent for 15 s counts as no progress.
  const patient = { signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) };
  try {
    const answer = await fetch(`${model}/metrics`, patient);
    const text = answer.ok ? await answer.text() : "";
    const processing = metric(text, "requests_processing");
    const tokens = metric(text, "kv_cache_tokens");
    if (processing !== undefined && tokens !== undefined) return { state: processing > 0 ? "busy" : "idle", tokens };
    const health = await fetch(`${model}/health`, patient).then(reply => (reply.ok ? reply.json() : {})).catch(() => ({}));
    return { state: Number(health?.slots_processing) > 0 ? "busy" : "idle" };
  } catch (error) {
    return (error as Error)?.name === "TimeoutError" ? { state: "busy", silent: true } : { state: "unknown" };
  }
}
