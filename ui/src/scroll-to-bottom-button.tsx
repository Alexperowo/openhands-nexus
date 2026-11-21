import type { ComponentProps } from "react";
import { ScrollToBottomButton as CanvasScrollToBottomButton } from "../node_modules/@openhands/agent-canvas/dist/components/shared/buttons/scroll-to-bottom-button.js";
import { ArrowDown } from "lucide-react";

export function ScrollToBottomButton({ onClick }: ComponentProps<typeof CanvasScrollToBottomButton>) {
  const label = "К новым сообщениям";
  return <button type="button" className="nexus-scroll-to-bottom" data-testid="scroll-to-bottom"
    aria-label={label} onClick={event => {
      const history = event.currentTarget.closest("[data-testid='chat-interface']")
        ?.querySelector<HTMLElement>("[data-testid='chat-scroll-container']");
      onClick();
      history?.focus({preventScroll: true});
    }}>
    <ArrowDown aria-hidden size={20} />{label}
  </button>;
}
