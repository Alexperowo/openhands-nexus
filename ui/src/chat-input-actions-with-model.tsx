import { type ComponentProps, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChatInputActions as CanvasChatInputActions } from "../node_modules/@openhands/agent-canvas/dist/components/features/chat/components/chat-input-actions.js";
import { useChatInputLlmProfileState } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-chat-input-llm-profile-state.js";
import { useReasoningLevel } from "./llm-profile-picker-with-reasoning";
import { REASONING } from "./reasoning";

export function ChatInputActions(props: ComponentProps<typeof CanvasChatInputActions>) {
  const { currentProfileName } = useChatInputLlmProfileState();
  const { level } = useReasoningLevel();
  const root = useRef<HTMLDivElement>(null);
  const [inlineTarget, setInlineTarget] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    const element = root.current;
    if (!element) return;
    // Canvas has no action slot. Its overflow button is the only menu trigger
    // without a test id. Portal into its wrapper so status stays after the button
    // when Canvas recreates it on resize, preserving Canvas's measurement refs.
    const syncTarget = () => setInlineTarget(element.querySelector<HTMLButtonElement>(
      "button[aria-haspopup='menu']:not([data-testid])",
    )?.parentElement ?? null);
    syncTarget();
    const observer = new MutationObserver(syncTarget);
    observer.observe(element, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);
  const status = `${currentProfileName}${level ? ` · ${REASONING[level].label}` : ""}`;
  return (
    <div ref={root} className="nexus-input-actions">
      <CanvasChatInputActions {...props} />
      {inlineTarget && currentProfileName && createPortal(
        <span className="nexus-model-status" data-testid="chat-input-model-status" title={status}>
          {status}
        </span>,
        inlineTarget,
      )}
    </div>
  );
}
