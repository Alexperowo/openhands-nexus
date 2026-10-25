import { useLayoutEffect, type ComponentProps } from "react";
import { ChatInputField as CanvasChatInputField } from "../node_modules/@openhands/agent-canvas/dist/components/features/chat/components/chat-input-field.js";
import { ConnectionBridge } from "./connection-bridge";

type Props = ComponentProps<typeof CanvasChatInputField>;

export function ChatInputField(props: Props) {
  useLayoutEffect(() => {
    const input = props.chatInputRef.current;
    if (!input) return;
    input.setAttribute("role", "textbox");
    input.setAttribute("aria-label", "Сообщение агенту");
    input.setAttribute("aria-multiline", "true");
    input.setAttribute("aria-disabled", String(Boolean(props.disabled)));
    input.tabIndex = props.disabled ? -1 : 0;
  }, [props.chatInputRef, props.disabled]);
  useLayoutEffect(() => {
    const root = props.chatInputRef.current?.closest("[data-testid='chat-interface']");
    if (!root) return;
    const label = () => {
      const button = root.querySelector("[data-testid='scroll-to-bottom']");
      if (button && button.getAttribute("aria-label") !== "К новым сообщениям") button.setAttribute("aria-label", "К новым сообщениям");
    };
    const observer = new MutationObserver(label);
    observer.observe(root, { childList: true, subtree: true });
    label();
    return () => observer.disconnect();
  }, [props.chatInputRef]);
  return <><ConnectionBridge /><CanvasChatInputField {...props} /></>;
}
