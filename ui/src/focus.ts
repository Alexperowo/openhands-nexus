const CONTROLS = "a[href], button, input, select, textarea, [contenteditable='true'], [tabindex]";

export function focusableElements(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(CONTROLS)].filter((element) =>
    element.tabIndex >= 0 && !element.matches(":disabled") &&
    !element.closest("[inert], [hidden], [aria-hidden='true']") &&
    element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden");
}

/** null means the browser can move focus normally; -1 means focus the empty scope. */
export function tabBoundary(count: number, index: number, backwards: boolean): number | null {
  if (!count) return -1;
  if (index < 0) return backwards ? count - 1 : 0;
  if (backwards && index === 0) return count - 1;
  if (!backwards && index === count - 1) return 0;
  return null;
}

export function focusPage(main = document.querySelector<HTMLElement>(".app-main")) {
  if (!main || main.closest("[inert]")) return;
  const target = [...main.querySelectorAll<HTMLElement>(
    ".settings-page h1, .settings-page h2, [data-testid='chat-input'][contenteditable='true']",
  )].find((element) => element.getClientRects().length && !element.closest("[inert]")) ?? main;
  if (!target.matches("[contenteditable='true']")) target.tabIndex = -1;
  target.focus();
}

/** Hide the background from both Tab and touch exploration; leave later modal portals alone. */
export function isolateDialog(root: HTMLElement, backdrop?: Element | null) {
  // Only what this call made inert is released: React may lift its own inert meanwhile,
  // and restoring a remembered value would lock that part again.
  const background: HTMLElement[] = [];
  for (let node: HTMLElement | null = root; node?.parentElement; node = node.parentElement) {
    for (const sibling of node.parentElement.children) {
      if (sibling instanceof HTMLElement && sibling !== node && sibling !== backdrop && !sibling.inert) {
        background.push(sibling);
        sibling.inert = true;
      }
    }
    if (node.parentElement === document.body) break;
  }
  const trap = (event: KeyboardEvent) => {
    if (event.key !== "Tab" || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    // Canvas opens nested dialogs and conversation menus in document.body portals.
    const target = event.target as Element | null;
    if (!root.contains(target) && target?.closest("[role='dialog'], [data-testid='context-menu']")) return;
    const controls = focusableElements(root);
    const index = tabBoundary(controls.length, controls.indexOf(document.activeElement as HTMLElement), event.shiftKey);
    if (index === null) return;
    event.preventDefault();
    (controls[index] ?? root).focus();
  };
  document.addEventListener("keydown", trap);
  return () => {
    document.removeEventListener("keydown", trap);
    for (const element of background) element.inert = false;
  };
}
