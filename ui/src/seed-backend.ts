// Run before active-store evaluates; storage itself does not initialize that store.
import { readStoredBackends, writeStoredBackends, writeStoredActiveBackend } from "../node_modules/@openhands/agent-canvas/dist/api/backend-registry/storage.js";
import { SEEDED_DEFAULT_BACKEND_ID } from "../node_modules/@openhands/agent-canvas/dist/api/backend-registry/default-backend.js";
import { originBackends, originLocation } from "./backend-origin.ts";

if (typeof window !== "undefined") {
  const current = readStoredBackends();
  const backends = originBackends(current, window.location.origin, SEEDED_DEFAULT_BACKEND_ID);
  if (backends !== current) writeStoredBackends(backends);
  writeStoredActiveBackend({ backendId: SEEDED_DEFAULT_BACKEND_ID, orgId: null });
  // Canvas gives URL selection priority over both sessionStorage and localStorage.
  const location = originLocation(window.location.href);
  if (location !== window.location.pathname + window.location.search + window.location.hash) {
    window.history.replaceState(window.history.state, "", location);
  }
}
