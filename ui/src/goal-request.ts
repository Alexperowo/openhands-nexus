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
