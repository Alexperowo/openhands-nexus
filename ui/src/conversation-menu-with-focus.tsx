import { useLayoutEffect, useRef, type ComponentProps, type KeyboardEvent } from "react";
import { ConversationCardContextMenu as CanvasConversationMenu } from "../node_modules/@openhands/agent-canvas/dist/components/features/conversation-panel/conversation-card/conversation-card-context-menu.js";
import { focusableElements } from "./focus";

type Props = ComponentProps<typeof CanvasConversationMenu>;

export function ConversationCardContextMenu(props: Props) {
  const root = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    opener.current = document.activeElement as HTMLElement;
    if (root.current) focusableElements(root.current)[0]?.focus();
  }, []);
  const restore = () => { if (opener.current?.isConnected) opener.current.focus(); };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Tab") {
      event.preventDefault();
      props.onClose();
      restore();
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !root.current) return;
    const controls = focusableElements(root.current);
    if (!controls.length) return;
    const index = controls.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? controls.length - 1
      : (index + (event.key === "ArrowDown" ? 1 : -1) + controls.length) % controls.length;
    event.preventDefault();
    controls[next].focus();
  };
  return (
    <div ref={root} onKeyDown={onKeyDown} onClickCapture={restore}>
      {/* Restore before the action: a newly opened confirmation remembers a live opener. */}
      <CanvasConversationMenu {...props} />
    </div>
  );
}
