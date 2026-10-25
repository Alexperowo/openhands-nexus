import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useLocation, useNavigate } from "react-router";
import { Accessibility, KeyRound, Settings, Sparkles, Volume2 } from "lucide-react";
import {
  AgentServerUIProviders,
  AppSettings,
  ConversationView,
  LLMSettings,
  SecretsSettings,
  Sidebar,
} from "@openhands/agent-canvas";
import { NavigationProvider } from "./navigation-context";
import { SidebarMobileNavProvider } from "./sidebar-mobile-nav-context";
import { audioService, useAudioStatus } from "./audio-service";
import { errorMessage } from "./api";
import { createConversation, latestConversationId } from "./conversations";
import { usePreferences } from "./preferences";
import { AccessibilitySettings, VoiceSettings } from "./settings-pages";
import { SettingsShell } from "./settings-shell";
import { StatusBar } from "./status-bar";
import { unlockCues } from "./status-cues";
import { useConversationSpeech } from "./use-conversation-speech";
import i18nInstance from "./i18n";
import { focusPage } from "./focus";
import { AudioControls } from "./audio-controls";
import { useMotion } from "./motion";
import { useNarrowSidebar } from "./narrow-sidebar";
import { useConnectionPhase } from "./connection-state";
import { observeCanvasAccessibility } from "./canvas-accessibility";
import { beginOpening, finishOpening, initialOpening, isNewConversationClick, isOpeningPath,
  mayShowOpened, NEW_CONVERSATION_SELECTOR, requestOpening } from "./conversation-opening.ts";

const SETTINGS_PAGES = [
  { to: "/settings", text: "SETTINGS$NAV_APPLICATION", icon: <Settings />, page: <AppSettings /> },
  { to: "/settings/llm", text: "SETTINGS$NAV_LLM", icon: <Sparkles />, page: <LLMSettings /> },
  { to: "/settings/secrets", text: "SETTINGS$NAV_SECRETS", icon: <KeyRound />, page: <SecretsSettings /> },
  { to: "/settings/voice", text: "NEXUS$NAV_VOICE", icon: <Volume2 />, page: <VoiceSettings /> },
  { to: "/settings/accessibility", text: "NEXUS$NAV_ACCESSIBILITY", icon: <Accessibility />, page: <AccessibilitySettings /> },
];
const SETTINGS_NAV = SETTINGS_PAGES.map(({ to, text, icon }) => ({
  type: "item" as const, item: { to, text, icon, subtitle: "" },
}));
// Browsers grant playback on click/keyup-like activation; a touch pointerdown does not count.
const GESTURES = ["click", "keydown"];

const conversationIdOf = (path: string) => path.match(/^\/conversations\/([a-zA-Z0-9_-]+)(?:\/|$)/)?.[1] ?? null;

export default function App() {
  const { pathname: currentPath } = useLocation();
  const routerNavigate = useNavigate();
  const conversationId = conversationIdOf(currentPath);
  const preferences = usePreferences();
  const audio = useAudioStatus();
  const { status, activity, model, error: pollingError, ready, cancel: cancelSpeech } = useConversationSpeech(conversationId);
  const motion = useMotion();
  useNarrowSidebar(preferences.fontSize);
  const connection = useConnectionPhase(conversationId, ready, pollingError);
  const [routeError, setRouteError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const opening = useRef(initialOpening(currentPath));
  const latestPath = useRef(currentPath);
  const main = useRef<HTMLElement>(null);
  const shell = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => shell.current ? observeCanvasAccessibility(shell.current) : undefined, []);
  const lastConversation = useRef<string | null>(null);
  useEffect(() => { if (conversationId) lastConversation.current = conversationId; }, [conversationId]);

  useEffect(() => {
    const changed = latestPath.current !== currentPath;
    latestPath.current = currentPath;
    // A closed drawer or a replaced page must not leave focus on a vanished element.
    const focused = document.activeElement;
    if (changed || !focused || focused === document.body || focused === main.current || !focused.isConnected) focusPage(main.current);
  }, [currentPath, ready, audio.isUnlocked]);

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    if (to === currentPath) return;
    // Stop at once, before an in-flight request can speak for the previous conversation.
    if (conversationIdOf(to) !== conversationId) cancelSpeech();
    routerNavigate(to, options);
  }, [routerNavigate, currentPath, conversationId, cancelSpeech]);
  const navigation = useMemo(() => ({
    currentPath, conversationId, isNavigating: false, navigate,
  }), [currentPath, conversationId, navigate]);

  // Browsers allow sound only after a gesture: the first touch or key anywhere enables it.
  useEffect(() => {
    const unlock = () => { void audioService.unlockAudio(); void unlockCues(); };
    for (const type of GESTURES) document.addEventListener(type, unlock, { capture: true });
    return () => {
      for (const type of GESTURES) document.removeEventListener(type, unlock, { capture: true });
    };
  }, []);

  useLayoutEffect(() => {
    document.documentElement.style.setProperty("--nexus-font-size", `${preferences.fontSize}px`);
  }, [preferences.fontSize]);
  useLayoutEffect(() => { document.documentElement.dataset.nexusMotion = motion; }, [motion]);

  const requestOpen = (path: string) => {
    opening.current = requestOpening(opening.current, path);
    setAttempt((value) => value + 1);
  };
  const newConversationClick = (event: MouseEvent<HTMLDivElement>) => {
    const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>(NEW_CONVERSATION_SELECTOR) : null;
    if (link && isNewConversationClick(event, { target: link.target, disabled: link.getAttribute("aria-disabled") === "true" })) {
      requestOpen("/conversations");
    }
  };

  // "/" opens the latest conversation; "/conversations" (Canvas "New chat") starts a new one.
  useEffect(() => {
    if (!isOpeningPath(currentPath) || opening.current.opening) return;
    const next = beginOpening(opening.current, currentPath);
    opening.current = next.state;
    const operation = next.operation;
    if (!operation) {
      setRouteError((error) => error || "Диалог не открылся. Нажмите «Повторить».");
      return;
    }
    setRouteError("");
    // Never aborted: a creation request already sent would leave an orphan conversation.
    const signal = new AbortController().signal;
    const target = currentPath === "/conversations"
      ? createConversation(signal)
      : latestConversationId(signal).then((id) => id ?? createConversation(signal));
    target
      // The user may have gone elsewhere meanwhile: then the result is kept, not forced on them.
      .then((id) => { if (mayShowOpened(opening.current, operation, latestPath.current)) routerNavigate(`/conversations/${id}`, { replace: true }); })
      .catch((error) => { if (mayShowOpened(opening.current, operation, latestPath.current)) setRouteError(errorMessage(error)); })
      .finally(() => {
        opening.current = finishOpening(opening.current, operation);
        setAttempt((value) => value + 1);
      });
  }, [currentPath, routerNavigate, attempt]);

  const styleOverrides = useMemo(() => {
    const highContrast = preferences.highContrast;
    return {
      "--oh-color-base": highContrast ? "#000000" : "#111116",
      "--oh-color-base-secondary": "#16161e",
      "--oh-color-content": "#ffffff",
      "--oh-color-content-2": "#ffffff",
      "--oh-background": highContrast ? "#000000" : "#111116",
      "--oh-foreground": "#ffffff",
      "--oh-contrast": "#ffffff",
      "--oh-contrast-foreground": "#000000",
      "--oh-surface": "#111115",
      "--oh-surface-foreground": "#ffffff",
      "--oh-surface-raised": "#22222d",
      "--oh-surface-deep": "#08080a",
      "--oh-overlay": "#16161e",
      "--oh-overlay-foreground": "#ffffff",
      "--oh-text-secondary": "#dddddf",
      "--oh-text-tertiary": "#d4d4d8",
      "--oh-text-dim": "#c4c4cc",
      "--oh-text-subtle": "#c4c4cc",
      "--oh-muted": "#d4d4d8",
      "--oh-border": "#888899",
      "--oh-border-input": "#888899",
      "--oh-border-width": highContrast ? "2px" : "1px",
      "--oh-field-border-width": highContrast ? "2px" : "1px",
      "--oh-focus": "#ffdd00",
    };
  }, [preferences.highContrast]);

  let content;
  if (currentPath === "/settings" || currentPath.startsWith("/settings/")) {
    const page = SETTINGS_PAGES.find(({ to }) => to === currentPath)?.page;
    const back = lastConversation.current ? `/conversations/${lastConversation.current}` : "/";
    content = (
      <SettingsShell currentPath={currentPath} navigationItems={SETTINGS_NAV} onBack={() => navigate(back)}>
        {page ?? <p>Раздел не найден.</p>}
      </SettingsShell>
    );
  } else if (conversationId) {
    content = ready
      ? <ConversationView key={conversationId} />
      : !pollingError && <p className="app-note" role="status">Подключение к диалогу…</p>;
  } else if (routeError) {
    content = (
      <div className="app-note">
        <p role="alert">{routeError}</p>
        <button type="button" className="nexus-button" onClick={() => requestOpen(currentPath)}>
          Повторить
        </button>
      </div>
    );
  } else {
    content = <p className="app-note" role="status">Открываю диалог…</p>;
  }

  return (
    <AgentServerUIProviders styleOverrides={styleOverrides} i18n={i18nInstance} analytics={false} theme="dark">
      <NavigationProvider value={navigation}>
        <SidebarMobileNavProvider>
          <div className="app" ref={shell} data-testid="nexus-shell-root" onClickCapture={newConversationClick}>
            <Sidebar />
            <div className="app-main" ref={main} tabIndex={-1} role={currentPath.startsWith("/settings") ? undefined : "main"}
              aria-label={currentPath.startsWith("/settings") ? undefined : "Основная область"} data-nexus-connection={connection}>
              {!currentPath.startsWith("/settings") && <h1 className="sr-only">Беседа с агентом</h1>}
              {/* One row for status and sound: on a 28 px tablet every line of chat counts.
                  After a restart answers stay silent until a touch; the sound button says so and is that touch. */}
              {conversationId && <div className="nexus-topbar">
                <StatusBar key={conversationId} status={status} activity={activity} model={model}
                  connection={connection} problems={[pollingError, audio.error].filter(Boolean)} />
                <AudioControls />
              </div>}
              <div className="nexus-page" key={conversationId ?? currentPath}>{content}</div>
            </div>
          </div>
        </SidebarMobileNavProvider>
      </NavigationProvider>
    </AgentServerUIProviders>
  );
}
