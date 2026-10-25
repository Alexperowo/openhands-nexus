import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";
import { disclosureTiming, useMotion } from "./motion";

// Closed by default, live streaming included: the status line already says the agent is thinking,
// and an open block would take most of the tablet screen. Opening it is one tap.
export function ReasoningBlock({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const motion = useMotion();
  const animation = useRef<Animation | null>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const closingRequested = useRef(false);
  useEffect(() => () => animation.current?.cancel(), []);
  useLayoutEffect(() => {
    if (motion === "full") return;
    animation.current?.cancel();
    if (closingRequested.current && detailsRef.current) {
      closingRequested.current = false;
      detailsRef.current.open = false;
      setExpanded(false);
    }
  }, [motion]);
  if (!content.trim()) return null;
  const toggle = (event: MouseEvent<HTMLElement>) => {
    const details = event.currentTarget.parentElement as HTMLDetailsElement;
    const body = details.querySelector<HTMLElement>(".nexus-reasoning-body");
    if (motion !== "full" || !body?.animate) return;
    event.preventDefault();
    animation.current?.cancel();
    if (!details.open || closingRequested.current) {
      closingRequested.current = false;
      details.open = true; setExpanded(true);
      animation.current = body.animate([{opacity: 1, transform: "translateY(-3px)"}, {opacity: 1, transform: "none"}],
        disclosureTiming());
    } else {
      closingRequested.current = true;
      const closing = body.animate([{transform: "none"}, {transform: "translateY(-3px)"}], disclosureTiming());
      animation.current = closing;
      void closing.finished.then(() => {
        if (animation.current === closing && closingRequested.current && details.isConnected) {
          closingRequested.current = false; details.open = false; setExpanded(false);
        }
      }, () => {});
    }
  };
  return <details ref={detailsRef} className="nexus-reasoning" open={expanded} onToggle={event => setExpanded(event.currentTarget.open)} aria-live="off">
    <summary onClick={toggle}>Рассуждения</summary>
    <div className="nexus-reasoning-body">{content}</div>
  </details>;
}
