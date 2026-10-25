// Dependency order matters: seed storage before active-store initializes its snapshot.
import "./seed-backend.ts";
import { getActiveBackend, getActiveSelection, getRegisteredBackends, setActiveSelection, setRegisteredBackends, subscribeActiveBackend } from "../node_modules/@openhands/agent-canvas/dist/api/backend-registry/active-store.js";
import { SEEDED_DEFAULT_BACKEND_ID } from "../node_modules/@openhands/agent-canvas/dist/api/backend-registry/default-backend.js";
import { isOriginSelection, originBackends } from "./backend-origin.ts";

if (typeof window !== "undefined") {
  // Host requests always use this origin; Canvas must use the same backend, including after a switch.
  let syncing = false;
  const syncBackend = () => {
    if (syncing) return;
    syncing = true;
    try {
      const current = getRegisteredBackends();
      const backends = originBackends(current, window.location.origin, SEEDED_DEFAULT_BACKEND_ID);
      if (backends !== current) setRegisteredBackends(backends);
      const selection = getActiveSelection();
      if (!isOriginSelection(getActiveBackend(), window.location.origin, SEEDED_DEFAULT_BACKEND_ID) ||
          selection?.backendId !== SEEDED_DEFAULT_BACKEND_ID || selection.orgId != null) {
        setActiveSelection({ backendId: SEEDED_DEFAULT_BACKEND_ID, orgId: null });
      }
    } finally { syncing = false; }
  };
  syncBackend();
  subscribeActiveBackend(syncBackend);

  // Pre-seed dictation endpoint ONLY if not already present
  try {
    const existing = JSON.parse(localStorage.getItem("openhands-transcription-endpoint") || "{}");
    if (!existing?.baseUrl) {
      localStorage.setItem("openhands-transcription-endpoint", JSON.stringify({
        baseUrl: `${window.location.origin}/v1`,
        model: "v3_ctc",
      }));
    }
  } catch (e) {
    console.warn("[init] Could not pre-seed transcription endpoint", e);
  }
}
