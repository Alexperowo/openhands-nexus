import { useEffect } from "react";
import { useSidebarStore } from "../node_modules/@openhands/agent-canvas/dist/stores/sidebar-store.js";

// Canvas docks the sidebar from a fixed 768 px but sizes it in rem (18.75rem): with the 28 px
// tablet font it took 525 of 800 px and left the input "Что вы…". Below this the chat would
// get fewer than CHAT_MIN_REM, so the sidebar folds to its icon rail.
const DOCKED = 768;
const SIDEBAR_REM = 18.75;
const CHAT_MIN_REM = 26;

export function shouldFoldSidebar(width: number, fontSize: number) {
  return width >= DOCKED && width - SIDEBAR_REM * fontSize < CHAT_MIN_REM * fontSize;
}

/** Folds once on entering a narrow layout; opening it again stays the user's choice until then. */
export function useNarrowSidebar(fontSize: number) {
  useEffect(() => {
    let narrow = false;
    const check = () => {
      const now = shouldFoldSidebar(window.innerWidth, fontSize);
      if (now && !narrow) useSidebarStore.getState().setCollapsed(true);
      narrow = now;
    };
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, [fontSize]);
}
