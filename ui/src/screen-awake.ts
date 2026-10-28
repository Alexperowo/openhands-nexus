/**
 * Keeps the screen on while the agent works. On the tablet a screen that went dark froze the
 * page: the agent's steps were neither received nor spoken until the owner touched it again.
 * The browser drops the lock whenever the page is hidden, so it is asked again on return.
 */
class ScreenAwake {
  private wanted = false;
  private lock: { released: boolean; release(): Promise<void> } | null = null;
  private asking = false;
  private listening = false;

  set(wanted: boolean) {
    if (wanted === this.wanted) return;
    this.wanted = wanted;
    if (!this.listening && typeof document !== "undefined") {
      this.listening = true;
      document.addEventListener("visibilitychange", () => void this.sync());
    }
    void this.sync();
  }

  private async sync() {
    const api = (globalThis.navigator as any)?.wakeLock;
    if (this.asking || !api) return;
    const held = this.lock?.released === false;
    if (!this.wanted) {
      if (held) await this.lock!.release().catch(() => {});
      this.lock = null;
      return;
    }
    if (held || document.visibilityState !== "visible") return;
    this.asking = true;
    try {
      this.lock = await api.request("screen");
    } catch {
      this.lock = null; // Not allowed here (battery saver, policy): the page works as before.
    } finally {
      this.asking = false;
    }
    if (!this.wanted) void this.sync(); // The work ended while the lock was being granted.
  }
}

export const screenAwake = new ScreenAwake();
