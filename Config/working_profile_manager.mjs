/**
 * OpenHands Local - Working Profile Manager
 * Location: Config/working_profile_manager.mjs
 * 
 * Update-resistant standalone module that handles:
 * - Loading all Working Profiles from %USERPROFILE%\.openhands\working-profiles\
 * - Maintaining persistent server-side active state in %USERPROFILE%\.openhands\working-profile-state.json
 * - Dispatching synchronized profile switches to Agent Server (:18000)
 * - Zero dependency on npm packages or internal agent-canvas files.
 */

import { readFileSync, writeFileSync, renameSync, readdirSync, existsSync, mkdirSync, copyFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { request as httpRequest } from "node:http";
import process from "node:process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const USER_HOME = process.env.USERPROFILE || process.env.HOME || (process.env.HOMEDRIVE && process.env.HOMEPATH ? join(process.env.HOMEDRIVE, process.env.HOMEPATH) : "");
const OPENHANDS_HOME = process.env.OPENHANDS_HOME || (USER_HOME ? join(USER_HOME, ".openhands") : join(__dirname, "..", ".openhands"));
const WORKING_PROFILES_DIR = join(OPENHANDS_HOME, "working-profiles");
const STATE_FILE = join(OPENHANDS_HOME, "working-profile-state.json");
const API_KEY_FILE = join(OPENHANDS_HOME, "agent-canvas", "api-key.txt");
const TEMPLATES_DIR = join(__dirname, "working-profile-templates");
const AGENT_SERVER_PORT = 18000;

export function getSessionApiKey() {
  try {
    if (existsSync(API_KEY_FILE)) {
      return readFileSync(API_KEY_FILE, "utf-8").trim();
    }
  } catch {}
  return "";
}

function seedTemplatesIfMissing() {
  try {
    if (!existsSync(WORKING_PROFILES_DIR)) {
      mkdirSync(WORKING_PROFILES_DIR, { recursive: true });
    }
    const existing = readdirSync(WORKING_PROFILES_DIR).filter((f) => f.endsWith(".json"));
    if (existing.length === 0 && existsSync(TEMPLATES_DIR)) {
      const templateFiles = readdirSync(TEMPLATES_DIR).filter((f) => f.endsWith(".json"));
      for (const tf of templateFiles) {
        copyFileSync(join(TEMPLATES_DIR, tf), join(WORKING_PROFILES_DIR, tf));
      }
      console.log(`[WorkingProfileManager] Auto-seeded ${templateFiles.length} working profile templates to ${WORKING_PROFILES_DIR}`);
    }
  } catch (err) {
    console.warn("[WorkingProfileManager] Template auto-seeding warning:", err.message);
  }
}

export function loadWorkingProfiles() {
  seedTemplatesIfMissing();
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
  const tmpFile = `${STATE_FILE}.tmp.${Date.now()}`;
  writeFileSync(tmpFile, JSON.stringify(state, null, 2), "utf-8");
  renameSync(tmpFile, STATE_FILE);
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
 * Safely switches the global Working Profile with strict validation and Agent Server sync.
 * Failure behavior:
 * - Validates target profile and reasoning mode first (invalid mode throws Error, never silent fallback).
 * - Synchronizes with Agent Server before touching disk state.
 * - Only modifies disk state and reports success when Agent Server accepts.
 */
export async function switchWorkingProfile(workingProfileId, reasoningModeId = null, updatedBy = "api") {
  // a) Validate target profile first
  const profiles = loadWorkingProfiles();
  const targetWp = profiles.find((p) => p.id === workingProfileId);
  if (!targetWp) {
    throw new Error(`Working profile '${workingProfileId}' not found.`);
  }

  let resolvedAgentProfileId = targetWp.default_agent_profile_id;
  let resolvedLlmProfileName = targetWp.default_llm_profile_name;
  let activeReasoningModeId = null;

  const reasoning = targetWp.reasoning || {};
  const supported = Boolean(reasoning.supported);
  const modes = reasoning.modes || [];

  if (reasoningModeId) {
    if (!supported) {
      // Profile does not support reasoning modes (e.g. Ornith)
      const allowedDefault = reasoning.default_mode_id || "direct";
      if (reasoningModeId !== allowedDefault && reasoningModeId !== "direct") {
        throw new Error(`Working profile '${workingProfileId}' does not support reasoning modes (requested: '${reasoningModeId}').`);
      }
      activeReasoningModeId = allowedDefault;
    } else {
      // Explicit reasoning_mode_id must be valid for supported profiles; no silent fallback
      const mode = modes.find((m) => m.id === reasoningModeId);
      if (!mode) {
        const validModes = modes.length > 0 ? modes.map((m) => `'${m.id}'`).join(", ") : "none";
        throw new Error(`Invalid reasoning_mode_id '${reasoningModeId}' for working profile '${workingProfileId}'. Valid modes: [${validModes}].`);
      }
      activeReasoningModeId = mode.id;
      if (mode.target_agent_profile_id) {
        resolvedAgentProfileId = mode.target_agent_profile_id;
      }
      if (mode.target_llm_profile_name) {
        resolvedLlmProfileName = mode.target_llm_profile_name;
      }
    }
  } else {
    // Default mode selection if none explicitly specified
    if (supported && modes.length > 0) {
      activeReasoningModeId = reasoning.default_mode_id || modes[0].id;
      const mode = modes.find((m) => m.id === activeReasoningModeId) || modes[0];
      if (mode.target_agent_profile_id) {
        resolvedAgentProfileId = mode.target_agent_profile_id;
      }
      if (mode.target_llm_profile_name) {
        resolvedLlmProfileName = mode.target_llm_profile_name;
      }
    } else {
      activeReasoningModeId = reasoning.default_mode_id || "direct";
    }
  }

  if (!resolvedAgentProfileId || !resolvedLlmProfileName) {
    throw new Error(`Working profile '${workingProfileId}' is missing resolved agent or LLM profile.`);
  }

  // b) Synchronize Agent Server before touching disk
  let agentServerResult = null;
  try {
    agentServerResult = await syncToAgentServer(resolvedAgentProfileId, resolvedLlmProfileName);
  } catch (err) {
    throw new Error(`Agent Server synchronization failed: ${err.message}. Working profile state was NOT changed.`);
  }

  if (!agentServerResult || !agentServerResult.ok) {
    const detail = agentServerResult?.body ? ` (HTTP ${agentServerResult.status}: ${agentServerResult.body})` : ` (HTTP ${agentServerResult?.status || "unknown"})`;
    throw new Error(`Agent Server rejected profile switch${detail}. Working profile state was NOT changed.`);
  }

  // c & d) Only update disk state after verified successful Agent Server sync
  const newState = {
    active_working_profile_id: targetWp.id,
    active_reasoning_mode_id: activeReasoningModeId,
    resolved_agent_profile_id: resolvedAgentProfileId,
    resolved_llm_profile_name: resolvedLlmProfileName,
    updated_by: updatedBy,
  };

  saveWorkingProfileState(newState);

  return {
    ok: true,
    state: newState,
    agent_server_synced: true,
  };
}
