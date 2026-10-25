import { useSyncExternalStore } from "react";

export interface Preferences {
  autoSpeak: boolean;
  speakSteps: boolean;
  voice: string;
  speed: number;
  /** Speech loudness relative to the device volume, 0–1. */
  volume: number;
  cues: boolean;
  fontSize: number;
  highContrast: boolean;
  motion: import("./motion").MotionPreference;
  /** Level for new conversations and model switches (reasoning.ts). */
  reasoning: import("./reasoning").ReasoningLevel;
}

const KEY = "nexus-preferences";
const DEFAULTS: Preferences = {
  autoSpeak: true, speakSteps: false, voice: "xenia", speed: 1, volume: 1, cues: true, fontSize: 20, highContrast: true, motion: "system", reasoning: "high",
};

function load(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    return { ...DEFAULTS, ...(saved && typeof saved === "object" ? saved : {}) };
  } catch {
    return DEFAULTS;
  }
}

let current = load();
const listeners = new Set<() => void>();

export function getPreferences() {
  return current;
}

/** Without automatic speech the existing preference selects the TalkBack signals mode. */
export function stateCuesEnabled(preferences: Pick<Preferences, "autoSpeak" | "cues">): boolean {
  return !preferences.autoSpeak || preferences.cues;
}

export function setPreferences(update: Partial<Preferences>) {
  current = { ...current, ...update };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Private mode: preferences live until reload.
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function usePreferences() {
  return useSyncExternalStore(subscribe, getPreferences, getPreferences);
}
