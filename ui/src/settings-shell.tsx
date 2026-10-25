import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { ArrowLeft, Menu } from "lucide-react";
import { SettingsLayout, SettingsNavigation } from "@openhands/agent-canvas";
import { focusPage, isolateDialog } from "./focus";

type NavigationItems = ComponentProps<typeof SettingsLayout>["navigationItems"];

// Canvas shows its settings sections only from 768px up; below that its own app
// pairs the page with a drawer (SettingsNavigation), which the host has to open.
const PHONE = "(max-width: 767px)";

function useIsPhone() {
  const [isPhone, setIsPhone] = useState(() => matchMedia(PHONE).matches);
  useEffect(() => {
    const query = matchMedia(PHONE);
    const update = () => setIsPhone(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return isPhone;
}

export function SettingsShell({ currentPath, navigationItems, onBack, children }: {
  currentPath: string;
  navigationItems: NavigationItems;
  onBack: () => void;
  children: ReactNode;
}) {
  const isPhone = useIsPhone();
  const [menuOpen, setMenuOpen] = useState(false);
  const openedAt = useRef<string | null>(null);
  const drawer = useRef<HTMLDivElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (!isPhone) setMenuOpen(false); }, [isPhone]);

  // A section picked in the drawer renders after the drawer closes (the router
  // commits later), so its heading takes focus once the new path arrives.
  useEffect(() => {
    setMenuOpen(false);
    if (openedAt.current === null || openedAt.current === currentPath) return;
    openedAt.current = null;
    // The commit that removes inert happens after this effect.
    const frame = requestAnimationFrame(() => focusPage());
    return () => cancelAnimationFrame(frame);
  }, [currentPath]);

  // The drawer is modal: the rest is inert while it is open, Escape closes it,
  // and a plain close returns focus to the button that opened it.
  useEffect(() => {
    if (!menuOpen || !isPhone) return;
    openedAt.current = currentPath;
    // SettingsNavigation also renders a desktop sidebar, hidden here; only the drawer counts.
    const nav = drawer.current?.querySelector("[data-testid='settings-navbar']");
    const release = drawer.current ? isolateDialog(drawer.current) : undefined;
    (nav?.querySelector<HTMLElement>("a[aria-current='page']") ?? nav?.querySelector<HTMLElement>("a"))?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) { event.preventDefault(); setMenuOpen(false); }
    };
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("keydown", close);
      release?.();
      // Wait for the drawer to turn inert; the URL already shows whether a section was picked.
      requestAnimationFrame(() => {
        if (location.pathname !== openedAt.current) return;
        openedAt.current = null;
        if (menuButton.current) menuButton.current.focus();
        else focusPage();
      });
    };
    // currentPath is read only when opening.
  }, [menuOpen, isPhone]);

  return (
    <div className="settings-shell">
      {isPhone && (
        <>
          <header className="settings-bar" inert={menuOpen}>
            <button type="button" className="icon-button" aria-label="Назад к диалогу" title="Назад к диалогу" onClick={onBack}>
              <ArrowLeft aria-hidden />
            </button>
            <h1>Настройки</h1>
            <button ref={menuButton} type="button" className="icon-button" aria-label="Разделы настроек"
              title="Разделы настроек" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
              <Menu aria-hidden />
            </button>
          </header>
          <div ref={drawer} inert={!menuOpen} role={menuOpen ? "dialog" : undefined}
            aria-modal={menuOpen ? true : undefined} aria-label="Разделы настроек" tabIndex={-1}>
            <SettingsNavigation isMobileMenuOpen={menuOpen} onCloseMobileMenu={() => setMenuOpen(false)}
              navigationItems={navigationItems} />
          </div>
        </>
      )}
      <div className="settings-page" inert={isPhone && menuOpen}>
        <SettingsLayout navigationItems={navigationItems}>{children}</SettingsLayout>
      </div>
    </div>
  );
}
