import { useCallback, useRef } from "react";
import { useGoalInterceptor as useCanvasGoalInterceptor } from "../node_modules/@openhands/agent-canvas/dist/hooks/chat/use-goal-interceptor.js";
import { startGoal } from "../node_modules/@openhands/agent-canvas/dist/hooks/mutation/conversation-mutation-utils.js";
import { useUserConversation } from "../node_modules/@openhands/agent-canvas/dist/hooks/query/use-user-conversation.js";
import { useAgentState } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-agent-state.js";
import { useConversationStore } from "../node_modules/@openhands/agent-canvas/dist/stores/conversation-store.js";
import { displayErrorToast } from "../node_modules/@openhands/agent-canvas/dist/utils/custom-toast-handlers.js";
import { GOAL_ROUNDS, goalObjective } from "./goal-request.ts";
import { CLOCK_SLACK_MS, userMessagesSince } from "./pending-resend.ts";

/**
 * Canvas sends a request as a goal only after "/goal"; here every plain request between runs
 * is one. The server then sends the text as the user's message itself, and «Готово» comes from
 * the judge instead of the agent's own word.
 */
export function useGoalInterceptor(conversationId: string | null, next: (text: string) => void) {
  const canvas = useCanvasGoalInterceptor(conversationId, next);
  const attachments = useConversationStore((state: any) => state.images.length + state.files.length);
  const mode = useConversationStore((state: any) => state.conversationMode);
  const { curAgentState } = useAgentState();
  const { data: conversation } = useUserConversation(conversationId);
  const latest = useRef({ next, conversation });
  latest.current = { next, conversation };

  return useCallback((text: string) => {
    const objective = goalObjective(text, { conversationId, agentState: curAgentState, attachments, mode });
    if (!objective || !conversationId) { canvas(text); return; }
    const sentAt = Date.now();
    startGoal(conversationId, { objective, max_iterations: GOAL_ROUNDS }).catch(async (error: any) => {
      // The server answered and started nothing (409: a run began meanwhile): send as usual.
      if (typeof error?.status === "number") { latest.current.next(text); return; }
      // No answer: the goal may have started, and a resend would run the request twice.
      try {
        const messages = await userMessagesSince(conversationId, latest.current.conversation,
          sentAt - CLOCK_SLACK_MS, () => false);
        if (!messages.some((message) => message.text.trim() === objective)) latest.current.next(text);
      } catch {
        displayErrorToast("Не удалось понять, дошла ли просьба. Посмотрите ленту и при необходимости отправьте её ещё раз.");
      }
    });
  }, [canvas, conversationId, curAgentState, attachments, mode]);
}
