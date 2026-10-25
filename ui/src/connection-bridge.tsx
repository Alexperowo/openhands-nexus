import { useEffect } from "react";
import { useUnifiedWebSocketStatus } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-unified-websocket-status.js";
import { useNavigation } from "./navigation-context";
import { publishSocket } from "./connection-state";
import { usePendingResend } from "./pending-resend";

// Mounted through the existing chat-input adapter, inside Canvas's socket provider.
export function ConnectionBridge() {
  const { conversationId } = useNavigation();
  const state = useUnifiedWebSocketStatus();
  useEffect(() => { if (conversationId) publishSocket(conversationId, state); }, [conversationId, state]);
  usePendingResend(conversationId, state);
  return null;
}
