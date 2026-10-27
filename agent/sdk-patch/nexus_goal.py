"""The agent-server's goal loop (POST /api/conversations/{id}/goal) as the honest «Готово».

The UI sends each plain request as a goal: after the agent finishes, a judge call of the same model
reads the run and decides whether the request is provably done; if not, the loop sends what is
missing and the agent continues, at most a few rounds. The SDK loop is kept; this adapts it:

- The judge sees the run from the goal's own request on, each tool output clipped and the whole
  bounded, with the commands the agent ran. The SDK renders the entire history, condensed steps
  included, without the commands: a long conversation would not fit the model's window. The last
  few messages before the request come along with the objective, so a short answer (a file name,
  "да") is judged against the request it answers.
- The judge knows the setting (a personal PC, a user who is not a programmer), answers in Russian,
  and says when only the user can continue: the loop then stops instead of pushing the agent.
- Its follow-up and resume messages are Russian and start with FOLLOWUP_MARK, which the UI uses to
  tell them from the user's own messages.
"""
import json
import re

FOLLOWUP_MARK = "Проверка Nexus:"
NEEDS_USER = "Нужно ваше решение: "
UNPARSED = "Judge verdict could not be parsed."
TOOL_OUTPUT_CHARS = 3000
CALL_CHARS = 600
TRANSCRIPT_CHARS = 60000
TRANSCRIPT_HEAD = 12000
CONTEXT_MESSAGES = 6
CONTEXT_MESSAGE_CHARS = 1500
CONTEXT_HEADER = "Earlier in this conversation (context for the request above, not part of it):"

JUDGE_CONTEXT = """

Setting: the agent works on the owner's personal Linux PC; the owner is not a programmer and
expects a working result. Evidence can be command output, file listings or contents, screenshots
the agent described, or the state of a program it checked. For a question or a conversation, a
direct and correct answer is the deliverable. A step that a safety rule ("Страж Nexus") refused,
reported honestly with the remaining options, is not something the agent can finish by itself.

The objective may be followed by earlier messages of the conversation. A short reply there (a
name, "yes", a choice) continues the request it answers: judge whether that request is now done.

If the rest can only be done by the owner (a decision, a choice, permission, information only they
have), add "needs_user": true to the JSON. Write "missing" in Russian, briefly and in plain words
the owner understands."""

FOLLOWUP_PROMPT = FOLLOWUP_MARK + """ задача ещё не выполнена (проверка {iteration}).
Не хватает: {missing}

Посмотри на настоящее состояние системы, не полагайся на память. Доделай недостающее и подтверди \
результат проверкой (команда, вывод, содержимое файла). Заканчивай, только когда всё подтверждено. \
Если без пользователя дальше нельзя, кратко объясни, что нужно от него, и закончи."""

RESUME_PROMPT = FOLLOWUP_MARK + """ продолжение прерванной задачи. Проверь настоящее состояние \
системы, не полагайся на память, и доведи исходную задачу до подтверждённого результата."""


def clip(text, limit):
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n[… пропущено {len(text) - limit} символов …]\n{text[-half:]}"


def message_text(event):
    from openhands.sdk.event import ActionEvent, MessageEvent
    from openhands.sdk.llm import content_to_str
    if isinstance(event, MessageEvent):
        return "\n".join(content_to_str(event.llm_message.content)).strip()
    if isinstance(event, ActionEvent) and event.tool_name == "finish":
        return str(getattr(event.action, "message", "") or "").strip()
    return ""


def objective_index(events, objective):
    """Index of the last user message that is the goal's request, or None."""
    from openhands.sdk.event import MessageEvent
    wanted = objective.strip()
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if isinstance(event, MessageEvent) and event.source == "user" and message_text(event) == wanted:
            return index
    return None


def since_objective(events, objective):
    """Events from the goal's request on; all when it is not found."""
    index = objective_index(events, objective)
    return list(events) if index is None else list(events[index:])


def earlier_context(events, objective):
    """The last few messages before the goal's request, each clipped."""
    index = objective_index(events, objective)
    turns = []
    for event in reversed(events[:index or 0]):
        text = message_text(event)
        if text:
            role = "user" if getattr(event, "source", "") == "user" else "assistant"
            turns.append(f"{role}: {clip(text, CONTEXT_MESSAGE_CHARS)}")
            if len(turns) == CONTEXT_MESSAGES:
                break
    return "\n\n".join(reversed(turns))


def render_transcript(events):
    from openhands.sdk.event import LLMConvertibleEvent
    from openhands.sdk.llm import content_to_str
    turns = []
    for message in LLMConvertibleEvent.events_to_messages(list(events)):
        if message.role == "system":
            continue
        text = "\n".join(content_to_str(message.content)).strip()
        if message.role == "tool":
            text = clip(text, TOOL_OUTPUT_CHARS)
        calls = [f"[{call.name}] {clip(call.arguments, CALL_CHARS)}" for call in message.tool_calls or []]
        text = "\n".join(part for part in [text, *calls] if part)
        if text:
            turns.append(f"{message.role}: {text}")
    transcript = "\n\n".join(turns)
    if len(transcript) > TRANSCRIPT_CHARS:
        tail = TRANSCRIPT_CHARS - TRANSCRIPT_HEAD
        transcript = (f"{transcript[:TRANSCRIPT_HEAD]}\n\n[… пропущена середина работы, "
                      f"{len(transcript) - TRANSCRIPT_CHARS} символов …]\n\n{transcript[-tail:]}")
    return transcript


def needs_user(message):
    """The judge's "needs_user" flag, read from the same JSON the SDK parser takes."""
    from openhands.sdk.llm import content_to_str
    raw = "\n".join(content_to_str(message.content)).strip()
    block = re.search(r"\{.*\}", raw, re.DOTALL)
    for candidate in [raw, block.group(0) if block else ""]:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data.get("needs_user") is True
    return False


def patch_judge(module):
    module.JUDGE_SYSTEM_PROMPT = module.JUDGE_SYSTEM_PROMPT + JUDGE_CONTEXT
    module._render_transcript = render_transcript
    parse = module._parse_verdict

    def _parse_verdict(message):
        verdict = parse(message)
        if verdict.missing == UNPARSED:
            return verdict.model_copy(update={"missing": "проверка не смогла прочитать свой ответ, нужен ещё один круг"})
        if not verdict.complete and needs_user(message) and not verdict.missing.startswith(NEEDS_USER):
            verdict = verdict.model_copy(update={"missing": NEEDS_USER + (verdict.missing or "ответ пользователя")})
        return verdict

    module._parse_verdict = _parse_verdict


def patch_controller(module):
    module.FOLLOWUP_PROMPT = FOLLOWUP_PROMPT
    judge = module.judge_goal

    def judge_goal(judge_llm, objective, events):
        context = earlier_context(events, objective)
        request = f"{objective}\n\n{CONTEXT_HEADER}\n{context}" if context else objective
        return judge(judge_llm, request, since_objective(events, objective))

    module.judge_goal = judge_goal
    decide = module.GoalController.on_run_finished

    def on_run_finished(self, events):
        step = decide(self, events)
        # Asking the agent again cannot replace the owner's answer.
        if isinstance(step, module.GoalContinue) and step.verdict.missing.startswith(NEEDS_USER):
            return module.GoalDone(outcome=module.GoalOutcome(
                status="capped", iterations=self.iteration, verdict=step.verdict))
        return step

    module.GoalController.on_run_finished = on_run_finished


def patch_event_service(module):
    module.RESUME_PROMPT = RESUME_PROMPT
