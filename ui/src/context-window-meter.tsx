import { useRef } from "react";
import { useContextWindowUsage } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-context-window-usage.js";
import { useCompactContextAction } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-compact-context-action.js";
import { useSelectConversationTab } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-select-conversation-tab.js";
import { ContextWindowRing } from "../node_modules/@openhands/agent-canvas/dist/components/features/chat/components/context-window-ring.js";
import { useEventStore } from "../node_modules/@openhands/agent-canvas/dist/stores/use-event-store.js";
import { useNavigation } from "./navigation-context";
import { retainContext, type ContextReading } from "./stream-presentation";

export function ContextWindowMeter() {
  const { conversationId } = useNavigation();
  const incoming = useContextWindowUsage();
  const loadedId = useEventStore((state) => state.loadedConversationId);
  const reading = useRef<ContextReading>({ id: null, usage: null, stale: false });
  reading.current = retainContext(reading.current, conversationId, loadedId === conversationId ? incoming : null);
  const { usage, stale } = reading.current;
  const { handleCompact, isCompacting, isDisabled } = useCompactContextAction(usage?.perTurnToken ?? 0);
  const { navigateToTab } = useSelectConversationTab();
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const percentage = usage ? Math.min(100, Math.round(100 * usage.perTurnToken / usage.contextWindow)) : null;
  const label = percentage === null ? "Контекст: данных пока нет" :
    `Контекст: ${percentage}%${stale ? ", последнее известное значение" : ""}`;
  const close = () => { if (details.current) details.current.open = false; summary.current?.focus(); };

  return (
    <details className="nexus-context" ref={details} aria-live="off" onKeyDown={(event) => {
      if (event.key === "Escape" && details.current?.open) { event.preventDefault(); event.stopPropagation(); close(); }
    }}>
      <summary ref={summary} aria-label={label} title={label}>
        {/* No data yet (a new conversation) is an empty ring: a "?" looked like a help button. */}
        <ContextWindowRing percentage={percentage ?? 0} />
      </summary>
      <div className="nexus-context-content">
        <p>{label}</p>
        {usage && <p>{usage.perTurnToken.toLocaleString("ru-RU")} / {usage.contextWindow.toLocaleString("ru-RU")} токенов</p>}
        <button type="button" className="nexus-button" disabled={!usage || isDisabled} onClick={handleCompact}>
          {isCompacting ? "Сжимаю контекст…" : "Сжать контекст"}
        </button>
        <button type="button" className="nexus-button" onClick={() => { close(); navigateToTab("usage"); }}>Использование</button>
      </div>
    </details>
  );
}
