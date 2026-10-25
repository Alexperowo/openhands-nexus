import { useCallback, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { anchorText, restoreReadingAnchor, ScrollFollow, type ReadingAnchor } from "./scroll-follow";

const READING_NODES = "article p, article pre, .nexus-reasoning-body, summary, [data-testid='generic-event-message-title']";

// Canvas's private hook has no resize observation and depends on its own reveal flag.
// One replacement keeps the existing scroll context and native jump button working.
export function useScrollToBottom(scrollRef: RefObject<HTMLElement | null>, _revealing = false) {
  const policy = useRef(new ScrollFollow());
  const [autoScroll, updateAuto] = useState(true);
  const [hitBottom, setHitBottom] = useState(true);
  const sync = useCallback(() => updateAuto(policy.current.following), []);
  const setAutoScroll = useCallback((value: boolean | ((current: boolean) => boolean)) => {
    const enabled = typeof value === "function" ? value(policy.current.following) : value;
    if (enabled) policy.current.latest(); else policy.current.userIntent(true);
    sync();
  }, [sync]);
  const scrollDomToBottom = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    policy.current.latest();
    const top = Math.max(0, element.scrollHeight - element.clientHeight);
    policy.current.target(top);
    element.scrollTop = top;
    setHitBottom(true); sync();
  }, [scrollRef, sync]);
  const onChatBodyScroll = useCallback((element: HTMLElement) => {
    setHitBottom(policy.current.scroll(element.scrollTop, element.scrollHeight, element.clientHeight));
    sync();
  }, [sync]);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const state = policy.current;
    let anchor: HTMLElement | null = null;
    let saved: (ReadingAnchor & {owner: string}) | null = null;
    const remember = () => {
      if (state.following) return;
      const top = element.getBoundingClientRect().top;
      const candidates = [...element.querySelectorAll<HTMLElement>(READING_NODES)];
      anchor = candidates.find(node => node.getBoundingClientRect().bottom > top + 1) ?? null;
      const owner = anchor?.closest<HTMLElement>("[data-nexus-event]");
      saved = anchor && owner ? {owner: owner.dataset.nexusEvent!, tag: anchor.tagName,
        prefix: anchorText(anchor.textContent), index: [...owner.querySelectorAll(READING_NODES)].indexOf(anchor)} : null;
      if (anchor) state.remember("visible", anchor.getBoundingClientRect().top - top);
    };
    const layout = () => {
      if (state.following) scrollDomToBottom();
      else {
        if (anchor && !anchor.isConnected && saved) {
          const owner = [...element.querySelectorAll<HTMLElement>("[data-nexus-event]")].find(node => node.dataset.nexusEvent === saved!.owner);
          anchor = owner ? restoreReadingAnchor([...owner.querySelectorAll<HTMLElement>(READING_NODES)], saved) : null;
        }
        if (anchor?.isConnected && anchor.getClientRects().length) {
          const offset = anchor.getBoundingClientRect().top - element.getBoundingClientRect().top;
          const correction = state.correction("visible", offset);
          if (Math.abs(correction) > 0.5) {
            const top = element.scrollTop + correction;
            state.target(top); element.scrollTop = top;
          }
        }
        setHitBottom(element.scrollHeight - element.clientHeight - element.scrollTop <= 24);
      }
      remember();
    };
    // ResizeObserver runs after layout, before paint. Do not defer the scroll to
    // the next RAF: that would expose one frame at the wrong reading position.
    const resized = new ResizeObserver(layout);
    const observe = () => {
      resized.disconnect(); resized.observe(element);
      for (const child of element.children) resized.observe(child);
      layout();
    };
    const mutations = new MutationObserver(observe);
    mutations.observe(element, {childList: true});
    observe();
    const wheel = (event: WheelEvent) => { state.userIntent(event.deltaY < 0); remember(); sync(); };
    let touchY = 0;
    const touchStart = (event: TouchEvent) => { touchY = event.touches[0]?.clientY ?? 0; };
    const touchMove = (event: TouchEvent) => {
      const next = event.touches[0]?.clientY ?? touchY;
      state.userIntent(next > touchY); touchY = next; remember(); sync();
    };
    const key = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement)?.closest("input,textarea,[contenteditable='true']")) return;
      if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) {
        state.userIntent(true); remember(); sync();
      }
    };
    const scrolled = () => { remember(); };
    element.addEventListener("wheel", wheel, {passive: true});
    element.addEventListener("touchstart", touchStart, {passive: true});
    element.addEventListener("touchmove", touchMove, {passive: true});
    element.addEventListener("keydown", key);
    element.addEventListener("scroll", scrolled, {passive: true});
    return () => {
      resized.disconnect(); mutations.disconnect();
      element.removeEventListener("wheel", wheel); element.removeEventListener("touchstart", touchStart);
      element.removeEventListener("touchmove", touchMove); element.removeEventListener("keydown", key); element.removeEventListener("scroll", scrolled);
    };
  }, [scrollRef, scrollDomToBottom, sync]);
  return { scrollRef, autoScroll, setAutoScroll, hitBottom, setHitBottom, scrollDomToBottom, onChatBodyScroll };
}
