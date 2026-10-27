import { useCallback, useEffect, useRef } from "react";
import { useGoalInterceptor as useCanvasGoalInterceptor } from "../node_modules/@openhands/agent-canvas/dist/hooks/chat/use-goal-interceptor.js";
import { startGoal } from "../node_modules/@openhands/agent-canvas/dist/hooks/mutation/conversation-mutation-utils.js";
import { useAgentState } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-agent-state.js";
import { useConversationStore } from "../node_modules/@openhands/agent-canvas/dist/stores/conversation-store.js";
import { displayErrorToast } from "../node_modules/@openhands/agent-canvas/dist/utils/custom-toast-handlers.js";
import { GOAL_ROUNDS, deliverGoal, goalAttempt, goalObjective } from "./goal-request.ts";

/**
 * Canvas sends a request as a goal only after "/goal"; here every plain request between runs
 * is one. The server then sends the text as the user's message itself, and «Готово» comes from
 * the judge instead of the agent's own word.
 *
 * Delivery: each send has its own attempt id, and a lost answer repeats the same attempt, which the
 * server starts once (agent/sdk-patch/nexus_goal.py). A refusal sends the text the usual way, but
 * only into the conversation it was written in. Leaving the page drops the repeats; what arrived
 * is in that conversation's feed.
 */
export function useGoalInterceptor(conversationId: string | null, next: (text: string) => void) {
  const canvas = useCanvasGoalInterceptor(conversationId, next);
  const attachments = useConversationStore((state: any) => state.images.length + state.files.length);
  const mode = useConversationStore((state: any) => state.conversationMode);
  const { curAgentState } = useAgentState();
  const latest = useRef({ next, conversationId });
  latest.current = { next, conversationId };
  useEffect(() => () => { latest.current.conversationId = null; }, []);

  return useCallback((text: string) => {
    const objective = goalObjective(text, { conversationId, agentState: curAgentState, attachments, mode });
    if (!objective || !conversationId) { canvas(text); return; }
    const body = { objective, max_iterations: GOAL_ROUNDS, attempt: goalAttempt() };
    deliverGoal(() => startGoal(conversationId, body)).then((delivery) => {
      if (delivery === "started") return;
      // Refused (409: a run began meanwhile): send as usual, while its conversation is still open.
      if (delivery === "refused" && latest.current.conversationId === conversationId) latest.current.next(text);
      else if (delivery === "refused") displayErrorToast("Просьба не отправлена: беседа сменилась. Отправьте её в той беседе ещё раз.");
      else displayErrorToast("Не удалось понять, дошла ли просьба. Посмотрите ленту и при необходимости отправьте её ещё раз.");
    });
  }, [canvas, conversationId, curAgentState, attachments, mode]);
}
