import { useEffect, useLayoutEffect, useState, useSyncExternalStore } from "react";

export type ConnectionPhase = "connecting" | "online" | "lost";
export type SocketState = "CONNECTING" | "OPEN" | "CLOSING" | "CLOSED";
const EMPTY = { id: null as string | null, state: "CONNECTING" as SocketState, seen: false, failed: false };
let current = EMPTY;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export function publishSocket(id: string, state: SocketState) {
  if (current.id === id && current.state === state) return;
  current = { id, state, seen: state === "OPEN" || (current.id === id && current.seen),
    failed: state !== "OPEN" && (state === "CLOSED" || state === "CLOSING" || (current.id === id && current.failed)) };
  for (const listener of listeners) listener();
}
export function connectionPhase(ready: boolean, error: string, socket: { state: SocketState; seen: boolean; failed?: boolean }, stalled = false): ConnectionPhase {
  if (error || stalled || socket.failed || (ready && socket.state === "CLOSED") || (socket.seen && socket.state !== "OPEN")) return "lost";
  return ready && socket.state === "OPEN" ? "online" : "connecting";
}
export function useConnectionPhase(id: string | null, ready: boolean, error: string) {
  useLayoutEffect(() => {
    current = { ...EMPTY, id };
    for (const listener of listeners) listener();
  }, [id]);
  const socket = useSyncExternalStore(subscribe, () => current.id === id ? current : EMPTY, () => EMPTY);
  const [deadline, setDeadline] = useState({id, expired: false});
  const online = socket.state === "OPEN";
  useEffect(() => {
    setDeadline({id, expired: false});
    if (!id || !ready || online) return;
    // Covers bootstrap failures before Canvas mounts the composer/socket bridge.
    const timer = setTimeout(() => setDeadline({id, expired: true}), 15000);
    return () => clearTimeout(timer);
  }, [id, ready, online]);
  return connectionPhase(ready, error, socket, deadline.id === id && deadline.expired && ready && !online);
}
/** One notice per outage, even across any number of reconnect attempts. */
export class ConnectionAnnouncements {
  private lost = false;
  update(phase: ConnectionPhase): "lost" | "restored" | null {
    if (phase === "lost" && !this.lost) { this.lost = true; return "lost"; }
    if (phase === "online" && this.lost) { this.lost = false; return "restored"; }
    return null;
  }
}
