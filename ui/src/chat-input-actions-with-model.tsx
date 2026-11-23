import { type ComponentProps } from "react";
import { ChatInputActions as CanvasChatInputActions } from "../node_modules/@openhands/agent-canvas/dist/components/features/chat/components/chat-input-actions.js";
import { useChatInputLlmProfileState } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-chat-input-llm-profile-state.js";
import { useReasoningLevel } from "./llm-profile-picker-with-reasoning";
import { REASONING } from "./reasoning";

export function ChatInputActions(props: ComponentProps<typeof CanvasChatInputActions>) {
  const { currentProfileName } = useChatInputLlmProfileState();
  const { level } = useReasoningLevel();
  return (
    <div className="nexus-input-actions">
      <CanvasChatInputActions {...props} />
      {currentProfileName && (
        <p className="nexus-model-status" data-testid="chat-input-model-status">
          {currentProfileName}{level && ` · ${REASONING[level].label}`}
        </p>
      )}
    </div>
  );
}
