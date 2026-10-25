import { useSyncExternalStore } from "react";
import { usePreferences } from "./preferences.ts";

export type MotionPreference = "system" | "full" | "reduced" | "off";
export type MotionMode = "full" | "reduced" | "off";
const query = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
const subscribe = (callback: () => void) => {
  query?.addEventListener("change", callback);
  return () => query?.removeEventListener("change", callback);
};
const snapshot = () => query?.matches ?? false;
export function resolveMotion(preference: MotionPreference, systemReduced: boolean): MotionMode {
  return preference === "system" ? systemReduced ? "reduced" : "full" : preference;
}
export function useMotion() {
  const { motion } = usePreferences();
  return resolveMotion(motion, useSyncExternalStore(subscribe, snapshot, () => false));
}

export function disclosureTiming() {
  const style = getComputedStyle(document.documentElement);
  return { duration: parseFloat(style.getPropertyValue("--nexus-motion-fast")) || 0,
    easing: style.getPropertyValue("--nexus-motion-ease").trim() || "linear" };
}
