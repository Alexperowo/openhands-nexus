"""Step ledger: the conversation condenser keeps every earlier step, compressed by its age.

The SDK condenser has the model retell the forgotten steps in its own words: a slow call to the
local model, and whatever the retelling left out is gone. Here the forgotten steps become a
ledger built from the events themselves, without a model call:

  the newest of them: each call with its arguments and a digest of the result (first and last
    lines; rejections and errors in full);
  the older ones: one line per step. The user's messages stay verbatim, rejections stay.

A ledger from an earlier condensation is folded in: its detailed steps shrink to their line and
the numbering goes on. The model's own summary stays where the context is really out of room
(hard_context_reset) and takes over when the ledger fails or outgrows its share.

The model's retelling may drop a ban or the current request, so it always comes under the
user's own words from the forgotten steps: their messages verbatim, up to PIN of the threshold,
and the agent's last reply. Each message is shown whole or not at all, never cut. When they do
not fit, all of them go verbatim to a file in OH_PERSISTENCE_DIR/nexus-user-words; the block
shows the first message and the newest ones that fit, counts the rest and tells the agent to
read that file before its next step. A later ledger or block takes the words back from that
file. Nothing keeps a whole endless conversation in the context: the steps between the user's
messages are compressed.

Condensation starts at 70% of the model's window instead of at the window itself (Nex 19G with
its 112K window at ~80K); agent/config/settings.json caps it at 160000 for the 224K models. Ours, not an upstream feature: the idea comes from Antigravity-Nexus.
"""
import contextvars
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from openhands.sdk.event import (ActionEvent, AgentErrorEvent, Condensation, CondensationSummaryEvent,
                                 MessageEvent, ObservationEvent, UserRejectObservation)
from openhands.sdk.llm import TextContent
from openhands.sdk.logger import get_logger

logger = get_logger(__name__)

SHARE = 0.7          # condense at this part of the model's window
DETAILED = 0.15      # the newest steps with details: up to this part of the threshold
CAP = 0.25           # the whole ledger; a bigger one gives way to the model's summary
CHARS_PER_TOKEN = 3  # cautious: Russian ~3.2, code ~4
PIN = 0.1            # the user's own words above the model's summary: up to this part of the threshold
HEADER = ("[STEP LEDGER — earlier steps of this session, compressed to save context. Every step is "
          "listed in order; user messages are verbatim; the newest steps have details. Treat these "
          "steps as already done; re-read a file or rerun a check if you need its exact content.]")
DETAIL = "    ¦ "    # detail lines; folding an old ledger drops them
TASKS = "[Task list at that point]"
PINNED = ("[USER'S OWN WORDS — the user's messages from the earlier part of this session, verbatim and "
          "in order. The goal, bans and decisions in them outrank the summary below.]")
REPLY = "[The agent's last reply to the user]"
SUMMARY = "[SUMMARY OF THE EARLIER WORK]"
LEFT_OUT = re.compile(r"…\[(\d+) earlier user messages left out to save room\]…")
# The user's messages that do not fit the pinned block, all of them, verbatim.
WORDS_DIR = Path(os.environ.get("OH_PERSISTENCE_DIR") or Path.home() / ".openhands") / "nexus-user-words"
WORDS_FILE = ("[USER'S OWN WORDS — every message of the user from the earlier part of this session, "
              "verbatim and in order.]")
SAVED = ("[Not every user message fits here. All of them, verbatim and in order, are in the file {path}. "
         "Read that whole file before your next step (in parts if the viewer shortens it): the goal, bans "
         "and decisions in the messages not shown here still hold.]")
SAVED_PATH = re.compile(r"^\[Not every user message fits here\. All of them, verbatim and in order, "
                        r"are in the file (.+?\.txt)\. ")
NOT_SAVED = ("[Not every user message fits here, and saving them to a file failed. Before anything risky, "
             "ask the user to repeat the goal and bans you may be missing.]")
BIG_ARGS = {"file_text", "old_str", "new_str"}
ANSI = re.compile(r"\x1b\[[0-9;:?]*[A-Za-z]|\x1b\][^\x07]*\x07")  # ":" — journalctl colors (38:5:185)
# The terminal appends these to every output; the exit code goes into the step's line instead.
TERMINAL_NOISE = re.compile(r"^\[(The command completed with exit code|Command finished with exit code"
                            r"|Current working directory:|Python interpreter:).*\]$")

# Set while get_condensation runs: the threshold of that check. hard_context_reset runs outside
# it, so it keeps the model's own summary.
threshold = contextvars.ContextVar("nexus_ledger_threshold", default=None)
# Set while hard_context_reset runs: the room for the user's words there.
reset_threshold = contextvars.ContextVar("nexus_reset_threshold", default=None)


def _text(content):
    parts, images = [], 0
    for item in content:
        if isinstance(item, TextContent):
            parts.append(item.text)
        else:
            images += 1
    text = ANSI.sub("", "\n".join(parts)).strip()
    if images:
        text += f"\n[{images} image(s) omitted; take a new screenshot if needed]"
    return text


def _short(text, limit):
    text = " ⏎ ".join(line.strip() for line in str(text).strip().splitlines() if line.strip())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _cut(text, limit):
    """Long text with its middle left out, line breaks kept."""
    return text if len(text) <= limit else text[:limit * 2 // 3] + "\n…[shortened]…\n" + text[-limit // 3:]


def _head_tail(text, head, tail, what):
    if len(text) < 800:
        return text
    lines = text.splitlines()
    if len(lines) <= head + tail + 1:
        return _cut(text, 800)
    return "\n".join(lines[:head] + [f"…[{len(lines) - head - tail} lines hidden: {what}]…"] + lines[-tail:])


def _args(action):
    try:
        args = json.loads(action.tool_call.arguments or "{}")
    except ValueError:
        return {}
    return args if isinstance(args, dict) else {}


def _brief(tool, args, limit):
    """The call in a few words."""
    if tool == "terminal":
        return (" (input)" if args.get("is_input") else "") + " $ " + _short(args.get("command", ""), limit // 2)
    if tool == "file_editor":
        brief = f" {args.get('command', '')} {args.get('path', '')}"
        if args.get("view_range"):
            brief += f" lines {args['view_range']}"
        if args.get("insert_line") is not None:
            brief += f" at line {args['insert_line']}"
        if isinstance(args.get("file_text"), str):
            brief += f" ({args['file_text'].count(chr(10)) + 1} lines)"
        return brief
    if tool == "task_tracker":
        tasks = args.get("task_list")
        return f" {args.get('command', '')}" + (f" ({len(tasks)} tasks)" if isinstance(tasks, list) else "")
    shown = []
    for key, value in args.items():
        if key in BIG_ARGS and isinstance(value, str):
            shown.append(f"{key}=<{value.count(chr(10)) + 1} lines>")
        else:
            shown.append(f"{key}={_short(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), limit // 3)}")
    return "(" + ", ".join(shown) + ")"


def _tasks(observation):
    tasks = getattr(observation, "task_list", None) or []
    return "\n".join(f"- [{task.status}] {task.title}" + (f" — {task.notes}" if task.notes else "")
                     for task in tasks) or None


def _outcome(tool, args, result, limit):
    """What the call gave: a few words for the step's line and the digest for its details."""
    if result is None:
        return " → no result", []
    if isinstance(result, UserRejectObservation):
        reason = result.rejection_reason.strip()
        # Safety guidance is durable state, not optional detail dropped on the next fold.
        return f" → REJECTED by {result.rejection_source}: " + reason.replace("\n", "\n   "), []
    if isinstance(result, AgentErrorEvent):
        return f" → ERROR: {_short(result.error, limit)}", [_cut(result.error, 1500)] if len(result.error) > limit else []
    observation = result.observation
    lines = [line for line in _text(result.to_llm_message().content).splitlines() if not TERMINAL_NOISE.match(line.strip())]
    text = "\n".join(lines).strip()
    exit_code = getattr(observation, "exit_code", None)
    words = []
    if getattr(observation, "is_error", False):
        words.append("ERROR")
    if exit_code not in (None, 0):
        words.append(f"exit {exit_code}")
    if not text:
        return f" → {', '.join(words + ['empty'])}", []
    count = len(text.splitlines())
    if tool == "file_editor" and args.get("command") != "view":
        line = _short(text.splitlines()[0], limit // 2)  # "The file … has been edited" or the error
    else:
        line = f"{count} lines; last: {_short(text.splitlines()[-1], limit // 2)}" if count > 1 else _short(text, limit // 2)
    if tool == "file_editor" and args.get("command") == "view":
        digest = _head_tail(text, 5, 5, f"view of {args.get('path', '')}; re-read it if needed")
    elif tool == "terminal":
        digest = _head_tail(text, 5, 12, "output; rerun if needed")
    else:
        digest = _head_tail(text, 5, 5, f"{tool} output")
    return f" → {', '.join(words + [line])}", [digest] if digest != line else []


def _fold(ledger):
    """An earlier ledger: its steps as lines (details dropped), its last number, its task list."""
    body, _, tasks = ledger[len(HEADER):].partition("\n" + TASKS + "\n")
    lines = [line for line in body.strip("\n").splitlines() if not line.startswith(DETAIL)]
    numbers = [int(found.group(1)) for line in lines if (found := re.match(r"#(\d+) ", line))]
    return lines, max(numbers, default=0), tasks.strip() or None


def _quote(text):
    return "USER: " + text.replace("\n", "\n   ")


def _left_out(count):
    return f"…[{count} earlier user messages left out to save room]…"


def _quoted(summary):
    """The user's words in an earlier ledger, pinned block or its file: their messages (str) and
    counts of left-out ones (int) in order, and the agent's last reply in a pinned block."""
    if summary.startswith(HEADER):
        start, reply = r"#\d+ USER: ", None
    elif summary.startswith(WORDS_FILE):
        start, reply = "USER: ", None
    elif summary.startswith(PINNED):
        summary = summary.partition("\n" + SUMMARY + "\n")[0]
        summary, _, reply = summary.partition("\n" + REPLY + "\n")
        start, reply = "USER: ", "\n".join(line[3:] for line in reply.splitlines()) or None
    else:
        return [], None
    items, current, saved = [], None, None
    for line in summary.splitlines()[1:]:
        if current is not None and line.startswith("   ") and not line.startswith(DETAIL):
            current.append(line[3:])
            continue
        current = None
        if found := re.match(start, line):
            current = [line[found.end():]]
            items.append(current)
        elif found := LEFT_OUT.search(line):
            items.append(int(found.group(1)))
        elif found := SAVED_PATH.match(line):
            saved = found.group(1)
    if saved:  # the file has them all; without it the block's own words and count
        try:
            return _quoted(Path(saved).read_text(encoding="utf-8"))[0], reply
        except OSError:
            logger.warning("Nexus: the user's words file %s is gone; only the pinned ones are carried", saved)
    return [item if isinstance(item, int) else "\n".join(item) for item in items], reply


def _save(items):
    """All the user's words in a file named by its content; its path, or None when it failed."""
    text = "\n".join([WORDS_FILE] + [_quote(item) if isinstance(item, str) else _left_out(item)
                                     for item in items]) + "\n"
    path = WORDS_DIR / (hashlib.sha256(text.encode()).hexdigest()[:16] + ".txt")
    try:
        WORDS_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temp = path.with_suffix(".part")
            temp.write_text(text, encoding="utf-8")
            os.replace(temp, path)
        return path
    except OSError:
        logger.exception("Nexus: the user's words were not saved to a file")
        return None


def _pinned(events, limit):
    """The user's own words from these events in PIN of the threshold, or None without any."""
    items, reply = [], None
    for event in events:
        if isinstance(event, MessageEvent):
            if event.source == "user":
                items.append(_text(event.llm_message.content))
            elif event.source == "agent":
                reply = _text(event.llm_message.content) or reply
        elif isinstance(event, ActionEvent) and event.tool_name == "finish":
            reply = str(_args(event).get("message") or "") or reply
        elif isinstance(event, CondensationSummaryEvent):
            found, earlier_reply = _quoted(event.summary)
            items += found
            reply = earlier_reply or reply
    words = [item for item in items if isinstance(item, str)]
    if not words and not reply:
        return None
    room = int(limit * PIN * CHARS_PER_TOKEN)
    if reply:
        reply = _cut(reply, min(2000, room // 4))
        room -= len(reply)
    out = [PINNED] + [_quote(item) if isinstance(item, str) else _left_out(item) for item in items]
    if sum(len(line) + 1 for line in out) > room + len(PINNED):
        # All of them go to a file. Here the first message, which usually sets the task, and then
        # the newest ones; each whole or not at all.
        path = _save(items)
        note = SAVED.format(path=path) if path else NOT_SAVED
        kept = [_quote(text) for text in words]
        room -= len(note) + 100
        first = [text for text in kept[:1] if len(text) <= max(room // 2, 300)]
        room -= sum(len(text) + 1 for text in first)
        # Going back from the newest one: out of room, the older ones stay out too, so an older
        # message never stands in for a newer one. One too long for this block on its own (a pasted
        # log, a document) is only counted in its place.
        whole, newest, skipped, placed = room, [], 0, 0
        for text in reversed(kept[1:]):
            if len(text) + 1 > whole:
                skipped += 1
                continue
            lines = ([_left_out(skipped)] if skipped else []) + [text]  # newest first
            if sum(len(line) + 1 for line in lines) > room:
                break
            room -= sum(len(line) + 1 for line in lines)
            newest += lines
            placed, skipped = placed + 1 + skipped, 0
        left_out = sum(item for item in items if isinstance(item, int)) + len(kept) - len(first) - placed
        out = [PINNED, note] + first + ([_left_out(left_out)] if left_out else []) + newest[::-1]
    if reply:
        out += [REPLY, "   " + reply.replace("\n", "\n   ")]
    return "\n".join(out)


def _pin(condensation, events, limit):
    """The model's summary under the user's own words from the forgotten events."""
    try:
        block = _pinned(events, limit or 80000)  # no limit known: as for a 112K window
    except Exception:  # an event shape this code does not know: the summary alone
        logger.exception("Nexus: the user's words were not pinned above the summary")
        return condensation
    if block is None:
        return condensation
    logger.info("Nexus: %d chars of the user's words above the model's summary", len(block))
    summary = f"{block}\n{SUMMARY}\n{(condensation.summary or '').strip()}"
    return condensation.model_copy(update={"summary": summary})


def _ledger(events, detail_chars, user_limit, line_limit):
    attached = {event.tool_call_id: event for event in events
                if isinstance(event, (ObservationEvent, UserRejectObservation, AgentErrorEvent))}
    called = {event.tool_call_id for event in events if isinstance(event, ActionEvent)}
    entries, number, tasks = [], 0, None  # entries: (lines of the step, its details)

    def step(head, details=()):
        nonlocal number
        number += 1
        entries.append(([f"#{number} {head}"], [detail for detail in details if detail]))

    for event in events:
        if isinstance(event, CondensationSummaryEvent):
            if event.summary.startswith(HEADER):
                lines, last, old_tasks = _fold(event.summary)
                # Its user messages stay whole; other steps get shorter when the ledger is squeezed.
                entries.append(([_short(line, line_limit * 3)
                                 if re.match(r"#\d+ (?!USER: )", line) and " → REJECTED by " not in line else line
                                 for line in lines], []))
                number, tasks = max(number, last), old_tasks
            else:  # the model's own summary: the user's words above it stay whole
                found, reply = _quoted(event.summary)
                for item in found:
                    step(_left_out(item) if isinstance(item, int) else _quote(item))
                summary = event.summary.partition("\n" + SUMMARY + "\n")[2] if found or reply else event.summary
                step("earlier summary:\n" + _cut(summary.strip(), user_limit * 2))
                if reply:
                    step("assistant (last reply before that summary): " + _short(reply, user_limit // 4),
                         [_cut(reply, 3000)] if len(reply) > user_limit // 4 else [])
        elif isinstance(event, MessageEvent):
            text = _text(event.llm_message.content)
            if event.source == "user":
                # Never silently cut a constraint out of the middle of the user's request.
                # If these messages alone exceed CAP, build() falls back to the SDK summary.
                step(_quote(text))
            else:  # the agent's answers carry its conclusions: more room than a tool step
                step("assistant: " + _short(text, user_limit // 4), [_cut(text, 3000)] if len(text) > user_limit // 4 else [])
        elif isinstance(event, ActionEvent) and event.tool_name in ("finish", "think"):
            text = str(_args(event).get("message") or _args(event).get("thought") or "")
            step(f"{event.tool_name}: " + _short(text, user_limit // 4), [_cut(text, 3000)] if len(text) > user_limit // 4 else [])
        elif isinstance(event, ActionEvent):
            args = _args(event)
            summary = args.pop("summary", None) or event.summary
            result = attached.get(event.tool_call_id)
            outcome, digest = _outcome(event.tool_name, args, result, line_limit)
            head = event.tool_name + _brief(event.tool_name, args, line_limit)
            # Without the model's own summary the SDK puts "tool: {arguments}" there: the brief says it.
            if summary and not summary.startswith(f"{event.tool_name}: "):
                head += f" — {_short(summary, 120)}"
            thought = _text(event.thought)
            call = []
            if event.tool_name == "terminal" and len(args.get("command", "")) > line_limit // 2:
                call.append("$ " + _cut(args["command"], 1500))
            call += [f"{key}:\n{_cut(value, 900)}" for key, value in args.items()
                     if key in BIG_ARGS and isinstance(value, str)]
            step(head + outcome, ([f"thought: {_short(thought, 400)}"] if thought else []) + call + digest)
            if event.tool_name == "task_tracker" and isinstance(result, ObservationEvent):
                tasks = _tasks(result.observation) or tasks
        elif isinstance(event, (ObservationEvent, UserRejectObservation, AgentErrorEvent)):
            if event.tool_call_id not in called:  # its call was condensed before
                outcome, digest = _outcome(event.tool_name, {}, event, line_limit)
                step(f"result of an earlier {event.tool_name} call{outcome}", digest)
        else:
            step(f"{type(event).__name__}: " + _short(_text(event.to_llm_message().content), line_limit))

    # The newest steps keep their details while they fit, older ones keep only their line.
    detailed, room = set(), detail_chars
    for index in range(len(entries) - 1, -1, -1):
        size = sum(len(detail) + len(DETAIL) * (detail.count("\n") + 1) for detail in entries[index][1])
        if size > room:
            break
        room -= size
        detailed.add(index)
    out = [HEADER]
    for index, (lines, details) in enumerate(entries):
        out += lines
        if index in detailed:
            out += [DETAIL + line for detail in details for line in detail.splitlines()]
    if tasks:
        out += [TASKS, tasks]
    return "\n".join(out)


def build(events, limit):
    """The ledger for these events at this threshold (tokens), or None when it outgrows its share."""
    cap = limit * CAP * CHARS_PER_TOKEN
    for user_limit, line_limit, details in ((4000, 240, 1.0), (1500, 160, 0.5), (600, 100, 0.0)):
        text = _ledger(events, int(limit * DETAILED * CHARS_PER_TOKEN * details), user_limit, line_limit)
        if len(text) <= cap:
            return text
    return None


def _condensation(events, summary_offset):
    limit = threshold.get()
    if limit is None:
        return None
    try:
        ledger = build(events, limit)
    except Exception:  # an event shape this code does not know: the model's summary instead
        logger.exception("Nexus ledger failed; the model will summarize")
        return None
    if ledger is None:
        logger.warning("Nexus ledger over %d%% of %d tokens; the model will summarize", CAP * 100, limit)
        return None
    logger.info("Nexus ledger: %d events -> %d chars (threshold %d tokens)", len(events), len(ledger), limit)
    return Condensation(forgotten_event_ids={event.id for event in events}, summary=ledger,
                        summary_offset=summary_offset, llm_response_id=f"nexus-ledger-{uuid.uuid4().hex}")


def install(module):
    """Patches the SDK's LLMSummarizingCondenser (module openhands.sdk.context.condenser.llm_summarizing_condenser)."""
    condenser = module.LLMSummarizingCondenser
    original_limit = condenser._effective_max_tokens
    original_get, original_aget = condenser.get_condensation, condenser.aget_condensation
    original_generate, original_agenerate = condenser._generate_condensation, condenser._agenerate_condensation
    original_reset, original_areset = condenser.hard_context_reset, condenser.ahard_context_reset

    def _effective_max_tokens(self, agent_llm):
        limit = original_limit(self, agent_llm)
        window = agent_llm.effective_max_input_tokens if agent_llm is not None else None
        if window:
            limit = min(limit or window, int(window * SHARE))
        return limit

    def get_condensation(self, view, agent_llm=None):
        token = threshold.set(self._effective_max_tokens(agent_llm))
        try:
            return original_get(self, view, agent_llm=agent_llm)
        finally:
            threshold.reset(token)

    async def aget_condensation(self, view, agent_llm=None):
        token = threshold.set(self._effective_max_tokens(agent_llm))
        try:
            return await original_aget(self, view, agent_llm=agent_llm)
        finally:
            threshold.reset(token)

    def hard_context_reset(self, view, agent_llm=None):
        token = reset_threshold.set(self._effective_max_tokens(agent_llm))
        try:
            return original_reset(self, view, agent_llm=agent_llm)
        finally:
            reset_threshold.reset(token)

    async def ahard_context_reset(self, view, agent_llm=None):
        token = reset_threshold.set(self._effective_max_tokens(agent_llm))
        try:
            return await original_areset(self, view, agent_llm=agent_llm)
        finally:
            reset_threshold.reset(token)

    def _generate_condensation(self, forgotten_events, summary_offset, max_event_str_length=None):
        return (_condensation(forgotten_events, summary_offset)
                or _pin(original_generate(self, forgotten_events, summary_offset, max_event_str_length),
                        forgotten_events, threshold.get() or reset_threshold.get() or self.max_tokens))

    async def _agenerate_condensation(self, forgotten_events, summary_offset, max_event_str_length=None):
        return (_condensation(forgotten_events, summary_offset)
                or _pin(await original_agenerate(self, forgotten_events, summary_offset, max_event_str_length),
                        forgotten_events, threshold.get() or reset_threshold.get() or self.max_tokens))

    condenser._effective_max_tokens = _effective_max_tokens
    condenser.get_condensation, condenser.aget_condensation = get_condensation, aget_condensation
    condenser._generate_condensation, condenser._agenerate_condensation = _generate_condensation, _agenerate_condensation
    condenser.hard_context_reset, condenser.ahard_context_reset = hard_context_reset, ahard_context_reset
