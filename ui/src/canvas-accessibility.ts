// Canvas 1.30.1 exposes no props for these two label defects. Keep the
// corrections in the host, scoped by test IDs, and observe late-mounted panels.
export function observeCanvasAccessibility(root: HTMLElement) {
  const update = () => {
    // Its content already names the button, including the visible shortcut.
    for (const trigger of root.querySelectorAll("[data-testid='command-menu-trigger']")) trigger.removeAttribute("aria-label");
    for (const selector of root.querySelectorAll("[data-testid='backend-selector']")) {
      const input = selector.querySelector("input");
      if (!input?.id || selector.querySelector("label")) continue;
      const label = document.createElement("label");
      label.htmlFor = input.id;
      label.className = "nexus-backend-label";
      label.textContent = "Сервер";
      // Downshift points at an absent label. Connect it to the visible host label.
      label.id = `${input.id}-nexus-label`;
      input.setAttribute("aria-labelledby", label.id);
      selector.prepend(label);
    }
  };
  const observer = new MutationObserver(update);
  observer.observe(root, {childList: true, subtree: true});
  update();
  return () => observer.disconnect();
}
