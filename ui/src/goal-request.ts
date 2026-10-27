// Which sent text becomes a goal (use-goal-by-default.ts); kept free of Canvas imports for the logic tests.

// Checks of «done?» before the loop stops and says what stays unconfirmed.
export const GOAL_ROUNDS = 3;
// Between runs only: a message to a working agent joins its run, as in Canvas.
const IDLE = new Set(["awaiting_user_input", "finished", "error"]);

export interface Composer { conversationId: string | null; agentState: string; attachments: number; mode: string }

/** The goal's objective, or "" when the text goes the usual way (commands, attachments, a running agent). */
export function goalObjective(text: string, composer: Composer) {
  const objective = text.trim();
  const plain = objective && !objective.startsWith("/") && !composer.attachments && composer.mode !== "plan";
  return composer.conversationId && plain && IDLE.has(composer.agentState) ? objective : "";
}

// Repeats of a goal start whose answer was lost: the server starts one attempt only once.
export const GOAL_RETRY_MS = [1000, 2000, 4000, 8000, 15000, 30000, 60000];

export type GoalDelivery = "started" | "refused" | "unknown";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** The id of one send: its repeats carry it, another send of the same text gets a new one. */
export function goalAttempt() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** Starts a goal. A lost answer (none at all, or a gateway error such as 502/504) does not tell
 *  whether the server took the request, so the same attempt goes again and the server starts it
 *  once. A 4xx answer is the server's own refusal: nothing started. Repeats used up: unknown. */
export async function deliverGoal(post: () => Promise<unknown>, wait = sleep, delays = GOAL_RETRY_MS): Promise<GoalDelivery> {
  for (let tries = 0; ; tries++) {
    try {
      await post();
      return "started";
    } catch (error: any) {
      const status = error?.status;
      if (typeof status === "number" && status >= 400 && status < 500 && status !== 408) return "refused";
      if (tries >= delays.length) return "unknown";
    }
    await wait(delays[tries]);
  }
}
