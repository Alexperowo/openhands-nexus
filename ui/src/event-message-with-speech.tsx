import React, { useRef } from "react";
import { EventMessage as CanvasEventMessage } from "../node_modules/@openhands/agent-canvas/dist/components/conversation-events/chat/event-message.js";
import { ChatMessage } from "../node_modules/@openhands/agent-canvas/dist/components/features/chat/chat-message.js";
import { isActionEvent, isStreamingDeltaEvent } from "../node_modules/@openhands/agent-canvas/dist/types/agent-server/type-guards.js";
import { CriticResultDisplay } from "../node_modules/@openhands/agent-canvas/dist/components/conversation-events/chat/event-message-components/critic-result-display.js";
import { ImageCarousel } from "../node_modules/@openhands/agent-canvas/dist/components/features/images/image-carousel.js";
import { useForkConversation } from "../node_modules/@openhands/agent-canvas/dist/hooks/mutation/use-fork-conversation.js";
import { displayErrorToast } from "../node_modules/@openhands/agent-canvas/dist/utils/custom-toast-handlers.js";
import { useNavigation } from "./navigation-context";
import { GitFork } from "lucide-react";
import { SpeakButton } from "./speak-button";
import { ReasoningBlock } from "./reasoning-block";
import { answerPresentation, type AnswerSource } from "./stream-presentation";
import { useSmoothText } from "./use-smooth-text";
import { speechText, type AgentEvent } from "./speech-events";

type Props = React.ComponentProps<typeof CanvasEventMessage>;

function StableAnswer({ event }: Pick<Props, "event">) {
  const streaming = isStreamingDeltaEvent(event);
  const wasStreamed = useRef(streaming);
  wasStreamed.current ||= streaming;
  const attempt = useRef(1);
  const lastReasoning = useRef("");
  if (streaming) {
    const nextAttempt = event.attempt ?? 1;
    if (nextAttempt !== attempt.current) lastReasoning.current = "";
    attempt.current = nextAttempt;
  }
  const raw = event as unknown as AnswerSource & {critic_result?: React.ComponentProps<typeof CriticResultDisplay>["criticResult"]};
  const parts = answerPresentation(raw);
  if (parts.reasoning) lastReasoning.current = parts.reasoning;
  const reasoning = parts.reasoning || (wasStreamed.current ? lastReasoning.current : "");
  const identity = `${event.id}:${attempt.current}`;
  const message = useSmoothText(parts.message, streaming, identity);
  const thought = useSmoothText(reasoning, streaming, identity);
  const complete = !streaming && message === parts.message;
  const spokenText = speechText(event as unknown as AgentEvent);
  const { conversationId, navigate } = useNavigation();
  const fork = useForkConversation();
  const forking = useRef(false);
  const content = raw.llm_message?.content;
  const images = Array.isArray(content) ? content.filter(part => part.type === "image").flatMap(part => part.image_urls ?? []) : [];
  return <>
    {(wasStreamed.current || reasoning) && <div className="nexus-reasoning-slot">
      <ReasoningBlock content={thought} />
    </div>}
    {/* Same component/article through delta -> durable; Markdown keeps its streaming mode until caught up. */}
    <ChatMessage type="agent" message={message} timestamp={event.timestamp} isFromPlanningAgent={event.isFromPlanningAgent}
      isStreaming={!complete} actions={event.kind === "MessageEvent" && conversationId ? [{ icon: <GitFork aria-hidden width={15} height={15} />,
        tooltip: "Продолжить отсюда в новой беседе", onClick: () => {
          if (forking.current || fork.isPending) return;
          forking.current = true;
          fork.mutate({sourceConversationId: conversationId, eventId: event.id}, {
            onSuccess: ({ info }) => navigate(`/conversations/${info.id}`),
            onError: () => displayErrorToast("Не удалось создать ответвление беседы. Попробуйте ещё раз."),
            onSettled: () => { forking.current = false; },
          });
        } }] : undefined}>
      {images.length > 0 && <ImageCarousel size="small" images={images} />}
    </ChatMessage>
    <div className="nexus-speech-slot">{!streaming && spokenText && <SpeakButton id={event.id} text={spokenText} />}</div>
    {raw.critic_result != null && <CriticResultDisplay criticResult={raw.critic_result} />}
  </>;
}

function EventMessageWithSpeech(props: Props) {
  const event = props.event;
  const answer = isStreamingDeltaEvent(event) || (event.kind === "MessageEvent" && event.source === "agent") ||
    (isActionEvent(event) && event.action.kind === "FinishAction");
  return <div className="nexus-event" data-nexus-event={event.id} aria-live={answer ? "off" : undefined}
    data-testid={isStreamingDeltaEvent(event) ? "nexus-stream" : undefined}>
    {answer ? <StableAnswer event={event} /> : <CanvasEventMessage {...props} />}
  </div>;
}
export const EventMessage = React.memo(EventMessageWithSpeech);
