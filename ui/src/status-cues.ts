export type Cue = "working" | "done" | "attention" | "error";

// Short distinct tone patterns: [frequency Hz, duration s].
const PATTERNS: Record<Cue, [number, number][]> = {
  working: [[440, 0.1]],
  done: [[523, 0.12], [784, 0.2]],
  attention: [[880, 0.1], [880, 0.1], [988, 0.18]],
  error: [[392, 0.18], [262, 0.3]],
};

const CUE_BY_STATUS: Record<string, Cue> = {
  running: "working",
  verified: "done",
  unverified: "done",
  unconfirmed: "attention",
  needs_user: "attention",
  stuck: "attention",
  awaiting_user_input: "attention",
  awaiting_user_confirmation: "attention",
  error: "error",
};

export const cueForStatus = (status: string): Cue | undefined => CUE_BY_STATUS[status];

let context: AudioContext | null = null;
let pendingConnection: Cue | null = null;

/** Call from a trusted user gesture, like audio unlock; resolves once tones can play. */
export async function unlockCues() {
  try {
    if (!context || context.state === "closed") context = new AudioContext();
    await context.resume();
    if (context.state === "running" && pendingConnection) {
      const cue = pendingConnection; pendingConnection = null; playCue(cue);
    }
    return context.state === "running";
  } catch {
    return false;
  }
}

/** Keep only the latest connection transition until the browser permits local sound. */
export function playConnectionCue(cue: Cue) {
  if (context?.state === "running") { pendingConnection = null; playCue(cue); }
  else pendingConnection = cue;
}

export function playCue(cue: Cue) {
  if (context?.state !== "running") return;
  let start = context.currentTime;
  for (const [frequency, duration] of PATTERNS[cue]) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = frequency;
    // Soft attack and release: no clicks.
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(0.25, start + 0.02);
    gain.gain.linearRampToValueAtTime(0, start + duration);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + duration);
    start += duration + 0.06;
  }
}
