import type { AgentEvent } from "./speech-events";

type StateEvent = AgentEvent & { key?: string; value?: unknown };

/** One frame of agent-server's session socket (openhands/agent_server/session_protocol.py). */
export interface SessionFrame {
  type?: string;
  seq?: number;
  through_seq?: number | null;
  event?: StateEvent;
}

/** How many of the last events are read on opening: the run state needs them, speech does not. */
export const HISTORY_EVENTS = 100;

/** The resume cursor for opening: the last HISTORY_EVENTS of a log with `count` events. */
export const openingCursor = (count: number) => Math.max(Number(count) - HISTORY_EVENTS - 1, -1);

/** Pages of state updates searched for the goal on opening: usage stats fill most of them. */
const GOAL_PAGES = 5;

/**
 * A goal check still running when the page opens, though it began before the history read: the
 * voice must hold the agent's answer until the verdict. The server marks a goal it no longer runs
 * as interrupted, so the latest goal event tells.
 */
export async function runningGoal(search: (query: string) => Promise<{ items: StateEvent[]; next_page_id?: string | null }>) {
  let pageId = "";
  for (let pages = 0; pages < GOAL_PAGES; pages++) {
    const page = await search("kind=ConversationStateUpdateEvent&sort_order=TIMESTAMP_DESC&limit=100" +
      (pageId && `&page_id=${encodeURIComponent(pageId)}`));
    const goal = page.items.find(event => event.key === "goal");
    if (goal) return (goal.value as { active?: unknown } | null)?.active ? goal : null;
    if (!page.next_page_id) return null;
    pageId = page.next_page_id;
  }
  return null;
}

/**
 * Reads the session socket (/sockets/session/{id}). A durable event carries its index in the
 * conversation log (seq), so reconnecting after the last seq loses and repeats nothing. Events up
 * to the log's end at the first connection are history: applied to the run state, never spoken.
 */
export class SessionEvents {
  private seen = new Set<string>();
  private historyEnd: number | null = null;
  status = "";
  /** The server's state snapshot arrived: status is the real one, not a guess from history. */
  statusKnown = false;
  /** The highest seq received: the resume cursor for the next connection. */
  lastSeq: number;

  constructor(cursor: number) {
    this.lastSeq = cursor;
  }

  take(frame: SessionFrame): { event: AgentEvent; fresh: boolean } | null {
    if (frame.type === "sync") {
      if (this.historyEnd === null) this.historyEnd = frame.through_seq ?? -1;
      return null;
    }
    const event = frame.event;
    if (!event || (frame.type !== "durable" && frame.type !== "transient")) return null;
    if (event.kind === "ConversationStateUpdateEvent") {
      // The snapshot sent on every connection is transient; status changes are durable.
      if (event.key === "full_state") {
        const status = (event.value as { execution_status?: unknown } | null)?.execution_status;
        if (typeof status === "string") this.status = status;
        this.statusKnown = true;
      } else if (event.key === "execution_status" && typeof event.value === "string") {
        this.status = event.value;
      }
    }
    if (frame.type !== "durable" || typeof frame.seq !== "number" || typeof event.id !== "string") return null;
    if (this.seen.has(event.id)) return null;
    this.seen.add(event.id);
    this.lastSeq = Math.max(this.lastSeq, frame.seq);
    return { event, fresh: this.historyEnd !== null && frame.seq > this.historyEnd };
  }
}
