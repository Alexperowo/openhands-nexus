import { useState } from "react";
import { useOptionalConversationId } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-conversation-id.js";
import { displayErrorToast } from "../node_modules/@openhands/agent-canvas/dist/utils/custom-toast-handlers.js";
import { isConversationStateUpdateEvent, isGoalConversationStateUpdateEvent } from "../node_modules/@openhands/agent-canvas/dist/types/agent-server/type-guards.js";
import { useEventStore } from "../node_modules/@openhands/agent-canvas/dist/stores/use-event-store.js";
import { useGoalStore } from "../node_modules/@openhands/agent-canvas/dist/stores/goal-store.js";
import { pauseConversation, resumeGoal, stopGoal } from "../node_modules/@openhands/agent-canvas/dist/hooks/mutation/conversation-mutation-utils.js";
import { chatInputPillButtonClassName, formControlDisabledClassName } from "../node_modules/@openhands/agent-canvas/dist/utils/form-control-classes.js";
import { cn } from "../node_modules/@openhands/agent-canvas/dist/utils/utils.js";
import CheckCircle from "../node_modules/@openhands/agent-canvas/dist/icons/check-circle-solid.js";
import XCircle from "../node_modules/@openhands/agent-canvas/dist/icons/x-circle-solid.js";
import { goalLine, type GoalStatus } from "./goal-request.ts";

const latestGoalEvent = (events: any[]) => {
  for (let index = events.length - 1; index >= 0; --index) {
    const event = events[index];
    if (isConversationStateUpdateEvent(event) && isGoalConversationStateUpdateEvent(event)) return event.id;
  }
};

/** Canvas's goal block put the whole request in its title, once per round: here one line that
 *  opens on a click, with the same stop and resume buttons. */
export function GoalStatusContent({ status, eventId }: { status: GoalStatus; eventId?: string }) {
  const { conversationId } = useOptionalConversationId();
  const goalActive = useGoalStore((state: any) => conversationId ? !!state.statusByConversation[conversationId]?.active : false);
  const latest = useEventStore((state: any) => eventId === undefined || latestGoalEvent(state.events) === eventId);
  const [busy, setBusy] = useState(false);
  const act = async (action: (id: string) => Promise<unknown>, failure: string) => {
    if (!conversationId || busy) return;
    setBusy(true);
    try {
      await action(conversationId);
    } catch (error) {
      displayErrorToast(error instanceof Error && error.message ? error.message : failure);
    } finally {
      setBusy(false);
    }
  };
  const button = (testId: string, label: string, onClick: () => void) => (
    <button type="button" data-testid={testId} disabled={busy} onClick={onClick}
      className={cn(chatInputPillButtonClassName, formControlDisabledClassName)}>{label}</button>
  );
  let trailing = null;
  if (conversationId && status.active) {
    trailing = button("goal-stop", "Остановить", () => act(async (id) => { await stopGoal(id); await pauseConversation(id); },
      "Не удалось остановить цикл цели"));
  } else if (conversationId && status.status === "interrupted" && latest && !goalActive) {
    trailing = button("goal-resume", "Продолжить", () => act(resumeGoal, "Не удалось продолжить цикл цели"));
  }
  const { line, details } = goalLine(status);
  const mark = status.active
    ? <span data-testid="goal-spinner" className="nexus-goal-mark inline-block w-3.5 h-3.5 rounded-full border-2 border-transparent border-t-border-input animate-spin" />
    : status.status === "complete"
      ? <CheckCircle data-testid="goal-done" className="nexus-goal-mark w-3.5 h-3.5 fill-success" />
      : <XCircle data-testid="goal-ended" className="nexus-goal-mark w-3.5 h-3.5 fill-muted" />;
  return (
    <div data-testid="goal-status" className="nexus-goal-row text-sm text-muted">
      <details className="nexus-goal">
        <summary title={line}>
          <span className="nexus-goal-chevron" aria-hidden="true">▸</span>
          {mark}
          <span className="nexus-goal-line">{line}</span>
        </summary>
        <p className="nexus-goal-details">{details}</p>
      </details>
      {trailing}
    </div>
  );
}
