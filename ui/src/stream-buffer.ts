/** A frame clock, not a character timer. Backlog accelerates delivery; no timers while idle. */
export class StreamBuffer {
  target = "";
  shown = "";
  private position = 0;
  private lastTime: number | null = null;
  private complete = true;

  targetText(text: string, immediate = false, complete = true) {
    this.complete = complete;
    if (immediate || !text.startsWith(this.shown)) {
      this.shown = text;
      this.position = text.length;
    }
    this.target = text;
    if (this.position >= text.length) this.shown = this.visible();
    if (this.done) this.lastTime = null;
  }
  get done() { return this.position >= this.target.length; }
  frame(time: number) {
    const elapsed = this.lastTime === null ? 16 : Math.max(0, time - this.lastTime);
    this.lastTime = time;
    // Typical bursts catch up before the next packet (~900ms in the fixture).
    // Backlog accelerates delivery; large packets do not land in one frame.
    this.position = Math.min(this.target.length, this.position + Math.max(0.5, (this.target.length - this.position) / 420) * elapsed);
    if (this.target.length - this.position < 1) this.position = this.target.length;
    this.shown = this.visible();
    if (this.done) this.lastTime = null;
    return this.shown;
  }
  private visible() {
    let end = Math.floor(this.position);
    // Never expose half a UTF-16 surrogate pair (emoji, some non-Latin scripts).
    if (end < this.target.length && /[\uD800-\uDBFF]/.test(this.target[end - 1] ?? "")) end--;
    // A growing partial word otherwise jumps onto the next line when it no
    // longer fits. Reveal complete words; never wait forever on long URLs/code.
    if (end < this.target.length || !this.complete) {
      const tail = /\S+$/.exec(this.target.slice(0, end));
      if (tail && tail[0].length < 48) end = tail.index;
    }
    return this.target.slice(0, end);
  }
}
