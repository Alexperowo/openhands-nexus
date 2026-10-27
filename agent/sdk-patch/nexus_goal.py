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
- Its verdict is read strictly. The SDK takes `bool(data["complete"])`, so the string "false" was a
  success. Here only the JSON value true with a score of at least COMPLETE_SCORE and no
  "needs_user" is complete; a wrong type, a missing field or a verdict that contradicts itself
  is not, and the agent gets another round with what was wrong.
- Its follow-up and resume messages are Russian and start with FOLLOWUP_MARK, which the UI uses to
  tell them from the user's own messages.
- The start takes the UI's id of that send ("attempt"). When the answer was lost, the UI sends the
  same attempt again; a repeat gets the first one's outcome, so a request never runs twice.
"""
import json
import math
import re

FOLLOWUP_MARK = "Проверка Nexus:"
NEEDS_USER = "Нужно ваше решение: "
COMPLETE_SCORE = 0.8
UNREADABLE = "проверка не смогла прочитать свой ответ, нужен ещё один круг"
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
the owner understands. "complete" is the JSON value true only when every requirement is proven
and the score is at least 0.8; otherwise it is false."""

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


def verdict_data(message):
    """The judge's JSON object, found the way the SDK parser finds it, or None."""
    from openhands.sdk.llm import content_to_str
    raw = "\n".join(content_to_str(message.content)).strip()
    block = re.search(r"\{.*\}", raw, re.DOTALL)
    for candidate in [raw, block.group(0) if block else ""]:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_verdict(message, verdict_class):
    data = verdict_data(message)
    if data is None:
        return verdict_class(score=0.0, complete=False, missing=UNREADABLE)
    score, complete, missing = data.get("score"), data.get("complete"), data.get("missing")
    missing = missing.strip() if isinstance(missing, str) else ""
    # bool is an int in Python; NaN and infinity are no probability.
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
        score = 0.0
    score = max(0.0, min(1.0, float(score)))
    if not isinstance(complete, bool):
        problem = "проверка ответила не по форме, нужен ещё один круг"
    elif complete and score < COMPLETE_SCORE:
        problem = f"проверка противоречит себе: «готово», но уверенность {score:.0%}; нужен ещё один круг"
    else:
        problem = ""
    if data.get("needs_user") is True:
        missing = missing if missing.startswith(NEEDS_USER) else NEEDS_USER + (missing or "ответ пользователя")
        return verdict_class(score=score, complete=False, missing=missing)
    if complete is True and not problem:
        return verdict_class(score=score, complete=True, missing=missing)
    missing = "; ".join(part for part in [missing, problem] if part)
    return verdict_class(score=score, complete=False, missing=missing or "проверка не назвала, чего не хватает: перепроверь результат")


def patch_judge(module):
    module.JUDGE_SYSTEM_PROMPT = module.JUDGE_SYSTEM_PROMPT + JUDGE_CONTEXT
    module._render_transcript = render_transcript
    module._parse_verdict = lambda message: parse_verdict(message, module.GoalVerdict)


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


ATTEMPTS = 200  # goal sends remembered for their repeats


def patch_goal_route(module):
    """POST .../goal with "attempt": a repeat of a started or starting send gets its outcome and
    starts nothing; a refused one may be tried again. In memory, for the last ATTEMPTS sends."""
    import asyncio
    from collections import OrderedDict
    from uuid import UUID
    from fastapi import Depends
    from pydantic import Field

    router, start = module.conversation_router, module.start_goal_in_conversation
    route = next(route for route in router.routes
                 if route.path == router.prefix + "/{conversation_id}/goal" and "POST" in route.methods)
    sends = OrderedDict()

    class StartGoalRequest(module.StartGoalRequest):
        attempt: str | None = Field(default=None, max_length=100,
                                    description="The client's id of this send; a repeat of it starts nothing.")

    async def start_goal_in_conversation(conversation_id: UUID, request: StartGoalRequest,
                                         conversation_service=Depends(module.get_conversation_service)
                                         ) -> module.Success:
        plain = module.StartGoalRequest(objective=request.objective, max_iterations=request.max_iterations)
        if not request.attempt:
            return await start(conversation_id, plain, conversation_service)
        key = (conversation_id, request.attempt)
        if key not in sends:
            sends[key] = asyncio.ensure_future(start(conversation_id, plain, conversation_service))
            sends[key].add_done_callback(lambda task: (task.cancelled() or task.exception()) and sends.pop(key, None))
            while len(sends) > ATTEMPTS:
                sends.popitem(last=False)
        # A dropped connection does not cancel the start itself.
        return await asyncio.shield(sends[key])

    index = router.routes.index(route)
    router.routes.remove(route)
    router.add_api_route("/{conversation_id}/goal", start_goal_in_conversation, methods=["POST"], name=route.name,
                         responses=route.responses, summary=route.summary, description=route.description)
    router.routes.insert(index, router.routes.pop())
