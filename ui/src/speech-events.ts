export interface AgentEvent {
  id: string;
  kind: string;
  source: string;
  tool_name?: string;
  action?: {
    kind?: string;
    message?: string;
    command?: string;
    path?: string;
    is_input?: boolean;
    task_list?: Array<{ title?: string; status?: string; notes?: string }>;
    args?: { message?: string; task_list?: unknown; [key: string]: unknown };
    [key: string]: unknown;
  };
  llm_message?: { role?: string; content?: { type: string; text?: string }[] };
  thought?: Array<{ type: string; text?: string }> | string;
  message?: string;
}

export interface EventPage {
  items: AgentEvent[];
  next_page_id?: string | null;
}

export function speechText(event: AgentEvent): string {
  if (event.source !== "agent") return "";
  if (event.kind === "ActionEvent" &&
      (event.tool_name === "finish" || event.action?.kind === "FinishAction")) {
    const text = event.action?.message ?? event.action?.args?.message;
    return typeof text === "string" ? stripThinking(text) : "";
  }
  if (event.kind !== "MessageEvent" || event.llm_message?.role !== "assistant") return "";
  // Only visible text; reasoning_content, thinking and extended_content are excluded.
  const content = event.llm_message.content;
  if (!Array.isArray(content)) return "";
  return stripThinking(content
    .filter((part) => part?.type === "text" && typeof part.text === "string")
    .map((part) => part.text).join("\n"));
}

// The model may leak reasoning inline; the chat hides it, so speech must too.
function stripThinking(text: string) {
  return text.replace(/<think>[\s\S]*?<\/think>/g, "").replace(/<think>[\s\S]*$/, "").trim();
}

// By ear a URL is noise; the domain alone says where it leads.
function replaceUrls(text: string): string {
  // Cyrillic never belongs to a URL the agent writes: "…/docs,затем" keeps "затем".
  return text.replace(/https?:\/\/[^\s)\]>"'`\u0400-\u04FF]+/g, (raw) => {
    const m = raw.match(/^(.*?)([.,;:!?)]*)$/);
    const url = m ? m[1] : raw;
    const trail = m ? m[2] : "";
    let domain = "";
    try {
      domain = new URL(url).hostname.replace(/^www\./i, "");
    } catch {
      const dm = url.match(/^https?:\/\/(?:www\.)?([^/:\s?#]+)/i);
      domain = dm ? dm[1] : url;
    }
    return domain + trail;
  });
}

// Only the file name: the directories are rarely what the listener needs.
function replacePaths(text: string): string {
  const pathRegex = /(?<=^|[\s(«"'`])(?:(?:~|\.\.|\.)\/(?:[a-zA-Z0-9_.\-\u0400-\u04FF]+\/)*[a-zA-Z0-9_.\-\u0400-\u04FF]+|\/(?:[a-zA-Z0-9_.\-\u0400-\u04FF]+\/)*[a-zA-Z0-9_.\-\u0400-\u04FF]+)/g;
  return text.replace(pathRegex, (raw) => {
    const m = raw.match(/^(.*?)([.,;:!?]*)$/);
    const p = m ? m[1] : raw;
    const trail = m ? m[2] : "";
    const name = p.substring(p.lastIndexOf("/") + 1);
    return name + trail;
  });
}

// Markdown is for the eyes: speak the words, not the markup.
export function forSpeech(text: string, full = false): string {
  if (full) {
    return text
      .replace(/```[^\n]*\n?([\s\S]*?)```/g, "$1")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 $2")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/(\*\*|__)(.+?)\1/g, "$2")
      .replace(/^#{1,6}\s+|^[*+\-]\s+/gm, "")
      .trim();
  }

  let res = text.replace(/```[\s\S]*?```/g, " Блок кода. ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    // The voice model takes **…** as its own emphasis markup and fails on it.
    .replace(/(\*\*|__)(.+?)\1/g, "$2")
    .replace(/^#{1,6}\s+|^[*+\-]\s+/gm, "");

  res = replaceUrls(res);
  res = replacePaths(res);
  res = res.replace(/`([^`]+)`/g, (_, code) => {
    const c = code.trim();
    return c.length <= 30 && !/[;{}()<>=]/.test(c) ? c : "код";
  });

  return res.trim();
}

// Natural clause boundaries prevent awkward TTS pauses mid-phrase.
function findClauseBoundary(s: string, lim: number): number {
  const minPos = lim / 2;
  let best = -1;
  const re = /(?:[,;:]\s|\s[—–]\s)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    if (m.index > lim) break;
    const cut = m.index + 1;
    if (cut <= lim && cut >= minPos) {
      best = cut;
    }
  }
  return best;
}

export function speechChunks(text: string, first = 150, rest = 400): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];

  const segmenter = new Intl.Segmenter("ru", { granularity: "sentence" });
  const rawSentences = [...segmenter.segment(trimmed)]
    .map((s) => s.segment.trim())
    .filter(Boolean);

  if (rawSentences.length === 0) return [];

  const chunks: string[] = [];
  let current = "";
  const currentLimit = () => (chunks.length === 0 ? first : rest);

  for (const sentence of rawSentences) {
    let s = sentence;
    if (current) {
      if (current.length + 1 + s.length <= currentLimit()) {
        current = current + " " + s;
        continue;
      }
      chunks.push(current);
      current = "";
    }

    while (s.length > currentLimit()) {
      const lim = currentLimit();
      let splitIdx = findClauseBoundary(s, lim);
      if (splitIdx <= 0) {
        splitIdx = s.lastIndexOf(" ", lim);
        if (splitIdx <= 0) {
          const nextSpace = s.indexOf(" ", lim);
          if (nextSpace > 0) {
            splitIdx = nextSpace;
          } else {
            const firstSpace = s.indexOf(" ");
            splitIdx = firstSpace > 0 ? firstSpace : s.length;
          }
        }
      }
      const part = s.slice(0, splitIdx).trim();
      s = s.slice(splitIdx).trim();
      if (part) chunks.push(part);
      if (!s) break;
    }

    if (s) {
      current = s;
    }
  }

  if (current) {
    chunks.push(current);
  }

  return chunks;
}

export function formatPlanCount(count: number): string {
  const rem10 = count % 10;
  const rem100 = count % 100;
  let word = "задач";
  if (rem100 < 11 || rem100 > 19) {
    if (rem10 === 1) word = "задача";
    else if (rem10 >= 2 && rem10 <= 4) word = "задачи";
  }
  return `План: ${count} ${word}`;
}

export function extractFileName(path: unknown): string {
  if (typeof path !== "string" || !path) return "";
  const clean = path.trim().replace(/[\\/]+$/, "");
  const base = clean.split(/[/\\]/).filter(Boolean).pop() ?? "";
  return base.length > 40 ? `${base.slice(0, 39)}…` : base;
}

export function clipStepExplanation(text: string): string {
  const cleaned = forSpeech(stripThinking(text));
  if (!cleaned) return "";
  const segmenter = new Intl.Segmenter("ru", { granularity: "sentence" });
  const sentences = [...segmenter.segment(cleaned)]
    .map((s) => s.segment.trim())
    .filter(Boolean);
  let first = sentences[0] || cleaned;
  if (first.length > 150) {
    let splitIdx = findClauseBoundary(first, 150);
    if (splitIdx <= 0) {
      splitIdx = first.lastIndexOf(" ", 150);
      if (splitIdx <= 0) {
        splitIdx = 150;
      }
    }
    first = first.slice(0, splitIdx).trim().replace(/[,;:—–\s]+$/, "");
  }
  return first;
}

export function extractStepExplanation(event: AgentEvent): string {
  let raw = "";
  if (Array.isArray(event.thought)) {
    raw = event.thought
      .filter((p) => p && p.type === "text" && typeof p.text === "string")
      .map((p) => p.text)
      .join("\n");
  } else if (typeof event.thought === "string") {
    raw = event.thought;
  } else if (event.action && event.action.kind !== "FinishAction") {
    if (typeof event.action.thought === "string") {
      raw = event.action.thought;
    } else if (typeof event.action.message === "string") {
      raw = event.action.message;
    } else if (typeof (event.action.args as Record<string, unknown> | undefined)?.message === "string") {
      raw = String((event.action.args as Record<string, unknown>).message);
    }
  } else if (typeof event.message === "string") {
    raw = event.message;
  }
  return raw ? clipStepExplanation(raw) : "";
}

export function actionSpeechPhrase(event: AgentEvent): string {
  const tool = event.tool_name ?? "";
  const action = (event.action ?? {}) as Record<string, unknown>;
  if (tool === "terminal") {
    if (action.is_input) return "Ввод в терминал";
    return "Выполняю команду";
  }
  if (tool === "file_editor" || tool === "planning_file_editor") {
    const name = extractFileName(action.path);
    if (action.command === "view") {
      return name ? `Читаю файл ${name}` : "Читаю файл";
    }
    return name ? `Правлю файл ${name}` : "Правлю файл";
  }
  if (tool === "apply_patch") return "Правлю файлы";
  if (tool === "glob") return "Поиск файлов";
  if (tool === "grep") return "Поиск в файлах";
  if (tool.startsWith("browser")) return "Работа в браузере";
  if (tool === "delegate" || tool === "task") return "Ожидание исполнителя";
  return "Выполняю действие";
}

function extractTaskList(event: AgentEvent): Array<{ title: string; status: string }> | null {
  const action = (event.action ?? {}) as Record<string, unknown>;
  let raw = action.task_list ?? (action.args as Record<string, unknown> | undefined)?.task_list;
  if (typeof raw === "string") {
    try { raw = JSON.parse(raw); } catch {}
  }
  if (Array.isArray(raw)) {
    return raw
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && typeof item.title === "string"))
      .map((item) => ({ title: String(item.title), status: String(item.status || "todo") }));
  }
  return null;
}

export class SpeechEvents {
  private initialized = false;
  private head: string | null = null;
  private turnTexts = new Set<string>();
  private knownTasks = new Map<string, string>();
  private handledStepIds = new Set<string>();

  seedHistory(history: AgentEvent[]) {
    for (const event of history) {
      if (event.tool_name === "task_tracker" || event.action?.kind === "TaskTrackerAction") {
        const tasks = extractTaskList(event);
        if (tasks) {
          for (const task of tasks) {
            this.knownTasks.set(task.title, task.status);
          }
        }
      }
    }
  }

  /** The first call only marks the head; its recent page goes to onHistory, never to speech. */
  async readNew(readPage: (pageId?: string, limit?: number) => Promise<EventPage>,
    onHistory?: (events: AgentEvent[]) => void) {
    if (!this.initialized) {
      const page = await readPage(undefined, 100);
      this.head = page.items[0]?.id ?? null;
      this.initialized = true;
      const history = [...page.items].reverse();
      this.seedHistory(history);
      onHistory?.(history);
      return [];
    }
    const events: AgentEvent[] = [];
    const pageIds = new Set<string>();
    let pageId: string | undefined;
    let newestId = this.head;
    let foundHead = this.head === null;
    do {
      const page = await readPage(pageId, 100);
      if (!pageId) newestId = page.items[0]?.id ?? this.head;
      const boundary = page.items.findIndex((event) => event.id === this.head);
      events.push(...(boundary < 0 ? page.items : page.items.slice(0, boundary)));
      if (boundary >= 0) { foundHead = true; break; }
      pageId = page.next_page_id || undefined;
      if (pageId && pageIds.has(pageId)) throw new Error("Сервер повторил страницу событий");
      if (pageId) pageIds.add(pageId);
    } while (pageId);
    if (!foundHead) throw new Error("История диалога изменилась. Откройте диалог заново");
    this.head = newestId;
    return events.reverse();
  }

  takeText(event: AgentEvent) {
    if (event.source === "user" && event.kind === "MessageEvent") this.turnTexts.clear();
    const text = speechText(event);
    const key = text.replace(/\s+/g, " ").trim();
    if (!key || this.turnTexts.has(key)) return "";
    // Finish and MessageEvent can contain the same answer under different IDs.
    this.turnTexts.add(key);
    return text;
  }

  takeStep(event: AgentEvent): string {
    if (event.source !== "agent" || event.kind !== "ActionEvent") return "";
    // Finish is the answer, think is internal reasoning; neither is a step phrase.
    if (event.tool_name === "finish" || event.action?.kind === "FinishAction") return "";
    if (event.tool_name === "think" || event.action?.kind === "ThinkAction") return "";
    if (this.handledStepIds.has(event.id)) return "";
    this.handledStepIds.add(event.id);

    // Plan updates
    if (event.tool_name === "task_tracker" || event.action?.kind === "TaskTrackerAction") {
      const tasks = extractTaskList(event);
      if (tasks) {
        return this.processPlanUpdate(tasks);
      }
    }

    // Step explanation if present
    const explanation = extractStepExplanation(event);
    if (explanation) return explanation;

    // Action phrase
    return actionSpeechPhrase(event);
  }

  private processPlanUpdate(tasks: Array<{ title: string; status: string }>): string {
    let newlyDoneTitle = "";
    for (const task of tasks) {
      const prev = this.knownTasks.get(task.title);
      if (task.status === "done" && prev !== "done") {
        newlyDoneTitle = task.title;
        break;
      }
    }
    for (const task of tasks) {
      this.knownTasks.set(task.title, task.status);
    }
    if (newlyDoneTitle) {
      const clean = forSpeech(newlyDoneTitle, false);
      return `Готово: ${clean}`;
    }
    return formatPlanCount(tasks.length);
  }
}
