export const RECONNECT_EVENT = "nexus:reconnect";
export function requestReconnect() {
  document.dispatchEvent(new Event(RECONNECT_EVENT));
}
