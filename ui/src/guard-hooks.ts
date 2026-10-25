// PreToolUse guard: stops commands that break the desktop session or Nexus itself and tells
// the agent the right way instead (nobody confirms actions, Aleksandr's decision). Canvas
// also starts conversations on its own (agent profile picker, plan mode, git bar, skill
// restart) without it, so the host adds the guard to every conversation start request.

const MATCHER = "terminal|file_editor|planning_file_editor";
const START_PATH = "/api/conversations";

type HookEntry = { hooks?: { command?: string }[] };

/** The guard first, then the hooks the workspace or the caller already asked for. */
export function withGuard(config: unknown, command: string): Record<string, unknown> {
  let base = config && typeof config === "object" ? config as Record<string, unknown> : {};
  // agent-server also accepts the {"hooks": {...}} wrapper and PascalCase event names.
  if (base.hooks && typeof base.hooks === "object" && Object.keys(base).length === 1) {
    base = base.hooks as Record<string, unknown>;
  }
  const { pre_tool_use: snake, PreToolUse: pascal, ...rest } = base;
  const others = [snake, pascal].flatMap(list => (Array.isArray(list) ? list as HookEntry[] : []))
    .filter(entry => !(entry?.hooks?.length && entry.hooks.every(hook => hook?.command === command)));
  return { ...rest, pre_tool_use: [{ matcher: MATCHER, hooks: [{ type: "command", command, timeout: 10 }] }, ...others] };
}

const isStart = (url: string, method: string | undefined, origin: string) =>
  (method ?? "GET").toUpperCase() === "POST" && new URL(url, origin).pathname === START_PATH;
const UNREADABLE = "Страж Nexus: тело запроса на запуск диалога нельзя прочитать";

/**
 * Request body with the guard added when this is a conversation start; anything else is
 * returned unchanged. A start whose body cannot be read throws: no unguarded conversation.
 */
export function guardedBody(url: string, method: string | undefined, body: unknown, origin: string, command: string) {
  if (!isStart(url, method, origin)) return body;
  if (typeof body !== "string") throw new Error(UNREADABLE);
  const payload = JSON.parse(body);
  return JSON.stringify({ ...payload, hook_config: withGuard(payload.hook_config, command) });
}

export function installGuardFetch(command: string) {
  const original = window.fetch.bind(window);
  window.fetch = (input, init) => {
    try {
      // A Request carries its body as a stream; Canvas and the host pass URL strings.
      if (input instanceof Request) {
        if (isStart(input.url, init?.method ?? input.method, window.location.origin)) throw new Error(UNREADABLE);
        return original(input, init);
      }
      const body = guardedBody(String(input), init?.method, init?.body, window.location.origin, command);
      return original(input, body === init?.body ? init : { ...init, body: body as BodyInit });
    } catch (error) {
      return Promise.reject(error);
    }
  };
}
