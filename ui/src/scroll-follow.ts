export interface ReadingAnchor { index: number; tag: string; prefix: string }
export const anchorText = (text: string | null) => (text ?? "").replace(/\s+/g, " ").trim().slice(0, 48);
/** Find the same paragraph after a Markdown subtree is finalized/replaced. */
export function restoreReadingAnchor<T extends {tagName: string; textContent: string | null}>(nodes: T[], saved: ReadingAnchor): T | null {
  const matches = (node: T) => node.tagName === saved.tag && anchorText(node.textContent).startsWith(saved.prefix);
  if (nodes[saved.index] && matches(nodes[saved.index])) return nodes[saved.index];
  return nodes.find(matches) ?? nodes[saved.index] ?? null;
}

/** DOM-independent policy: user intent wins over layout and programmatic scroll events. */
export class ScrollFollow {
  following = true;
  private lastTop = 0;
  private intendedTop: number | null = null;
  private anchor: { key: string; offset: number } | null = null;
  userIntent(upwards: boolean) { if (upwards) this.following = false; }
  scroll(top: number, height: number, viewport: number) {
    const nearBottom = height - viewport - top <= 24;
    const programmatic = this.intendedTop !== null && Math.abs(top - this.intendedTop) <= 2;
    if (!programmatic && top < this.lastTop - 1) this.following = false;
    if (nearBottom) this.following = true;
    this.intendedTop = null;
    this.lastTop = top;
    return nearBottom;
  }
  remember(key: string, offset: number) { this.anchor = { key, offset }; }
  correction(key: string, offset: number) {
    return !this.following && this.anchor?.key === key ? offset - this.anchor.offset : 0;
  }
  target(top: number) { this.intendedTop = top; this.lastTop = top; }
  latest() { this.following = true; this.anchor = null; }
}
