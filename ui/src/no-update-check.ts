// Replaces Canvas's api/agent-canvas-updates.js: the tablet must not ask registry.npmjs.org
// for new versions on every visit, and Canvas is upgraded deliberately, not from a card.
export const AGENT_CANVAS_RELEASE_NOTES_URL = "https://github.com/OpenHands/OpenHands/releases";
export const AGENT_CANVAS_UPDATE_COMMANDS = { npm: "", docker: "" };
export async function fetchLatestAgentCanvasVersion(): Promise<string> {
  throw new Error("Update check is disabled in OpenHands-Nexus");
}
