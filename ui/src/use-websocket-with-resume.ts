import { useCallback, useEffect, useRef } from "react";
import { useWebSocket as useCanvasWebSocket } from "../node_modules/@openhands/agent-canvas/dist/hooks/use-websocket.js";
import { RECONNECT_EVENT } from "./connection-events.ts";

// Canvas disconnect() disables retries. On resume, its provider can still report
// OPEN until the queued close event arrives, so reconnectIfStale() skips recovery.
export function useWebSocket(...args: Parameters<typeof useCanvasWebSocket>) {
  const [url, options] = args;
  const socket = useCanvasWebSocket(...args);
  const { disconnect, reconnect } = socket;
  const suspended = useRef(false);
  const forceReconnect = useCallback(() => {
    suspended.current = false;
    reconnect();
  }, [reconnect]);
  const suspend = useCallback(() => {
    suspended.current = Boolean(url.trim());
    disconnect();
  }, [url, disconnect]);

  useEffect(() => {
    suspended.current = false;
    if (!url.trim()) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const resume = () => {
      clearTimeout(timer);
      // Let Canvas's own resume run first. If it reconnected, the flag is cleared.
      // Otherwise restore retries even while its rendered state is still OPEN.
      timer = setTimeout(() => { if (suspended.current) forceReconnect(); }, 0);
    };
    const visible = () => { if (document.visibilityState === "visible") resume(); };
    const manual = () => {
      clearTimeout(timer);
      forceReconnect();
    };
    document.addEventListener("resume", resume);
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("pageshow", resume);
    document.addEventListener(RECONNECT_EVENT, manual);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("resume", resume);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("pageshow", resume);
      document.removeEventListener(RECONNECT_EVENT, manual);
    };
  }, [url, options?.connectionKey, forceReconnect]);

  return { ...socket, disconnect: suspend, reconnect: forceReconnect };
}
