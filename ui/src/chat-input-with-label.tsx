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
  return <><ConnectionBridge /><CanvasChatInputField {...props} /></>;
}
