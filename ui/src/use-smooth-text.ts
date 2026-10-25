import { useLayoutEffect, useRef, useState } from "react";
import { StreamBuffer } from "./stream-buffer";
import { useMotion } from "./motion";

export function useSmoothText(text: string, streaming: boolean, identity: string) {
  const motion = useMotion();
  const state = useRef<{ identity: string; buffer: StreamBuffer; streamed: boolean } | null>(null);
  if (!state.current || state.current.identity !== identity) {
    const buffer = new StreamBuffer();
    buffer.targetText(streaming ? "" : text, true);
    state.current = { identity, buffer, streamed: streaming };
  }
  const [, render] = useState(0);
  const current = state.current;
  current.streamed ||= streaming;
  useLayoutEffect(() => {
    const buffer = current.buffer;
    const previous = buffer.shown;
    const immediate = motion !== "full" || !current.streamed || document.visibilityState === "hidden";
    buffer.targetText(text, immediate, immediate || !streaming);
    let frame = 0;
    const tick = (time: number) => {
      const before = buffer.shown;
      if (buffer.frame(time) !== before) render(value => value + 1);
      if (!buffer.done) frame = requestAnimationFrame(tick);
    };
    if (buffer.done && buffer.shown !== previous) render(value => value + 1);
    else if (!buffer.done) frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text, streaming, motion, current]);
  return current.buffer.shown;
}
