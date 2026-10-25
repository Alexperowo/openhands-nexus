import React from "react";
import { useNavigation } from "./navigation-context";
import { focusableElements, focusPage, isolateDialog } from "./focus";

// Host copy of Canvas src/components/features/sidebar/sidebar-mobile-nav-context.tsx:
// the published build drops the provider but keeps the hook (narrow screens crash without it).

interface SidebarMobileNavContextValue {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
}

const SidebarMobileNavContext = React.createContext<SidebarMobileNavContextValue | null>(null);

export function SidebarMobileNavProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = React.useState(false);
  const { currentPath } = useNavigation();
  const path = React.useRef(currentPath);
  path.current = currentPath;
  const open = React.useCallback(() => setIsOpen(true), []);
  const close = React.useCallback(() => setIsOpen(false), []);
  const toggle = React.useCallback(() => setIsOpen((prev) => !prev), []);
  React.useEffect(() => {
    if (!isOpen) return;
    const opener = document.activeElement as HTMLElement;
    const openedPath = path.current;
    let drawer: HTMLElement | null = null;
    let release: (() => void) | undefined;
    const attach = () => {
      const element = document.querySelector<HTMLElement>("[data-testid='sidebar-mobile-drawer']");
      if (drawer || !element || element.getAttribute("aria-hidden") === "true") return;
      drawer = element;
      drawer.inert = false;
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-modal", "true");
      drawer.tabIndex = -1;
      release = isolateDialog(drawer, drawer.previousElementSibling);
      (focusableElements(drawer).find((control) => control.dataset.testid === "sidebar-mobile-drawer-close") ?? drawer).focus();
    };
    // Canvas mounts the drawer and makes it visible in two separate effects.
    const observer = new MutationObserver(attach);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-hidden"] });
    attach();
    const desktop = matchMedia("(min-width: 768px)");
    const resized = () => { if (desktop.matches) close(); };
    desktop.addEventListener("change", resized);
    return () => {
      observer.disconnect();
      desktop.removeEventListener("change", resized);
      release?.();
      // Canvas keeps the closing drawer mounted during its animation.
      if (drawer) drawer.inert = true;
      if (path.current === openedPath && opener?.isConnected) opener.focus();
      else focusPage();
    };
  }, [isOpen, close]);
  const value = React.useMemo(() => ({ isOpen, open, close, toggle }), [isOpen, open, close, toggle]);
  return <SidebarMobileNavContext.Provider value={value}>{children}</SidebarMobileNavContext.Provider>;
}

export function useSidebarMobileNav(): SidebarMobileNavContextValue {
  const context = React.useContext(SidebarMobileNavContext);
  if (!context) throw new Error("useSidebarMobileNav must be used within SidebarMobileNavProvider");
  return context;
}
