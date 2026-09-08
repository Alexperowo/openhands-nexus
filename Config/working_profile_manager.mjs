/**
 * OpenHands Local - Working Profile Manager
 * Location: K:\Project\Config\working_profile_manager.mjs
 * 
 * Update-resistant standalone module that handles:
 * - Loading all Working Profiles from C:\Users\User\.openhands\working-profiles\
 * - Maintaining persistent server-side active state in C:\Users\User\.openhands\working-profile-state.json
 * - Dispatching synchronized profile switches to Agent Server (:18000)
 * - Zero dependency on npm packages or internal agent-canvas files.
 */

import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { request as httpRequest } from "node:http";

const WORKING_PROFILES_DIR = "C:\\Users\\User\\.openhands\\working-profiles";
const STATE_FILE = "C:\\Users\\User\\.openhands\\working-profile-state.json";
const API_KEY_FILE = "C:\\Users\\User\\.openhands\\agent-canvas\\api-key.txt";
const AGENT_SERVER_PORT = 18000;

export function getSessionApiKey() {
  try {
    if (existsSync(API_KEY_FILE)) {
      return readFileSync(API_KEY_FILE, "utf-8").trim();
    }
  } catch {}
  return "";
}

export function loadWorkingProfiles() {
  const profiles = [];
  if (!existsSync(WORKING_PROFILES_DIR)) {
    return profiles;
  }
  const files = readdirSync(WORKING_PROFILES_DIR).filter((f) => f.endsWith(".json"));
  for (const file of files) {
    try {
      const fullPath = join(WORKING_PROFILES_DIR, file);
      const data = JSON.parse(readFileSync(fullPath, "utf-8"));
      profiles.push(data);
    } catch (err) {
      console.warn("[WorkingProfileManager] Error reading " + file + ":", err.message);
    }
  }
  return profiles;
}

export function getWorkingProfileState() {
  if (existsSync(STATE_FILE)) {
    try {
      const state = JSON.parse(readFileSync(STATE_FILE, "utf-8"));
      return state;
    } catch (err) {
      console.warn("[WorkingProfileManager] Error reading " + STATE_FILE + ":", err.message);
    }
  }
  // Safe default
  return {
    active_working_profile_id: "team-full",
    active_reasoning_mode_id: "standard_team",
    resolved_agent_profile_id: "ba66f66f-f9fb-4764-b5b9-22f27bf84b3a",
    resolved_llm_profile_name: "Qwen3.8-Medium",
    updated_at: new Date().toISOString(),
    updated_by: "default_fallback",
  };
}

export function saveWorkingProfileState(state) {
  state.updated_at = new Date().toISOString();
  writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), "utf-8");
}

/**
 * Dispatches an internal PATCH /api/settings to OpenHands Agent Server (127.0.0.1:18000)
 */
export async function syncToAgentServer(agentProfileId, llmProfileName) {
  const apiKey = getSessionApiKey();
  const payload = JSON.stringify({
    active_agent_profile_id: agentProfileId,
    active_profile: llmProfileName,
  });

  return new Promise((resolve, reject) => {
    const req = httpRequest(
      {
        hostname: "127.0.0.1",
        port: AGENT_SERVER_PORT,
        path: "/api/settings",
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
          "x-session-api-key": apiKey,
        },
        timeout: 5000,
      },
      (res) => {
        let body = "";
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve({ ok: true, status: res.statusCode, body });
          } else {
            resolve({ ok: false, status: res.statusCode, body });
          }
        });
      }
    );

    req.on("error", (err) => {
      reject(err);
    });

    req.write(payload);
    req.end();
  });
}

/**
 * Atomically switches the global Working Profile
 */
export async function switchWorkingProfile(workingProfileId, reasoningModeId = null, updatedBy = "api") {
  const profiles = loadWorkingProfiles();
  const targetWp = profiles.find((p) => p.id === workingProfileId);
  if (!targetWp) {
    throw new Error("Working profile '" + workingProfileId + "' not found.");
  }

  let resolvedAgentProfileId = targetWp.default_agent_profile_id;
  let resolvedLlmProfileName = targetWp.default_llm_profile_name;
  let activeReasoningModeId = reasoningModeId || targetWp.reasoning?.default_mode_id || "direct";

  if (targetWp.reasoning && targetWp.reasoning.supported && targetWp.reasoning.modes) {
    const mode = targetWp.reasoning.modes.find((m) => m.id === activeReasoningModeId);
    if (mode) {
      if (mode.target_agent_profile_id) {
        resolvedAgentProfileId = mode.target_agent_profile_id;
      }
      if (mode.target_llm_profile_name) {
        resolvedLlmProfileName = mode.target_llm_profile_name;
      }
    } else {
      activeReasoningModeId = targetWp.reasoning.default_mode_id || targetWp.reasoning.modes[0]?.id || "direct";
    }
  }

  const newState = {
    active_working_profile_id: targetWp.id,
    active_reasoning_mode_id: activeReasoningModeId,
    resolved_agent_profile_id: resolvedAgentProfileId,
    resolved_llm_profile_name: resolvedLlmProfileName,
    updated_by: updatedBy,
  };

  // 1. Persist state on disk
  saveWorkingProfileState(newState);

  // 2. Synchronize to Agent Server
  let agentServerResult = null;
  try {
    agentServerResult = await syncToAgentServer(resolvedAgentProfileId, resolvedLlmProfileName);
  } catch (err) {
    console.warn("[WorkingProfileManager] Could not sync to Agent Server:", err.message);
  }

  return {
    state: newState,
    agent_server_synced: agentServerResult?.ok ?? false,
  };
}
