"""The agent-server's goal loop (POST /api/conversations/{id}/goal) as the honest «Готово».

The UI sends each plain request between runs here. A short call of the conversation's model first
reads what the message is: a task for this PC gets a goal, one plain sentence of what must be true
when it is done (the UI shows it); talk, an instruction for the future or a request too unclear to
act on goes to the agent as a usual message, with no goal and no judge. The agent always gets the
owner's own words. After a goal's run a judge call of the same model reads the run and decides
whether the request is provably done; if not, the loop sends what is missing and the agent
continues, at most a few rounds. The SDK loop is kept; this adapts it:

- The judge sees the run from the goal's own request on, each tool output clipped and the whole
  bounded, with the commands the agent ran. The SDK renders the entire history, condensed steps
  included, without the commands: a long conversation would not fit the model's window. The last
  few messages before the request come along with the objective, so a short answer (a file name,
  "да") is judged against the request it answers. The judge gets the owner's words with the goal;
  extras the agent itself offered are no requirement (it had demanded a monitor the agent proposed).
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
import sys

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

The objective may give the owner's request in their own words and the goal as the assistant
understood it: judge against the owner's words. Extras the agent itself offered or suggested
(monitoring, further improvements) are not requirements. A symptom removed by switching off a
useful function the owner did not agree to give up is not a repair.

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

REQUEST_AND_GOAL = """The owner's request, in their own words:
{request}

The goal as the assistant understood it (only to read the request, not more than it):
{goal}"""

UNDERSTAND_SECONDS = 90  # a model that is not loaded yet starts within this
UNDERSTAND_SYSTEM = """You read the owner's newest message to the assistant that works on their \
personal Linux PC, together with the conversation before it, and decide what the message is.

"task": the owner wants something done or found out on this PC: fix, set up, change, install, \
find, check, build, clean up. A question whose answer needs looking at this PC ("why does X keep \
popping up?") is a task too: find the cause and, when the owner clearly wants it gone, remove it.
"talk": a greeting, thanks, a remark or an opinion; a standing instruction, a rule or a role for \
the assistant ("from now on you are responsible for..."); a question answered from general \
knowledge, without this PC; a request too unclear to act on without asking the owner first.

For a task write "goal": one short sentence in Russian, in plain words, saying what must be true \
when the owner's request is done, as the owner means it. Use the conversation to resolve "it", \
"this", "there". Do not add work the owner did not ask for and do not drop any part of the request.
For talk, "goal" is "".

Answer with JSON only: {"kind": "task" or "talk", "goal": "..."}"""

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


class Goal(str):
    """The understood goal (shown and judged) that keeps the owner's own words (sent to the agent)."""

    def __new__(cls, goal, request):
        value = super().__new__(cls, goal)
        value.request = request
        return value


def objective_index(events, objective):
    """Index of the owner's message the goal started from, or None.

    It is the first user message after the goal's starting status (round 0), a resume message
    aside; the goal's text itself, the way older goals were sent, is searched when there is none."""
    from openhands.sdk.event import ConversationStateUpdateEvent, MessageEvent
    found, armed = None, False
    for index, event in enumerate(events):
        if isinstance(event, ConversationStateUpdateEvent) and event.key == "goal":
            value = event.value if isinstance(event.value, dict) else {}
            armed = bool(value.get("active")) and value.get("iteration") == 0 and value.get("objective") == objective
        elif armed and isinstance(event, MessageEvent) and event.source == "user":
            armed = False
            if not message_text(event).startswith(FOLLOWUP_MARK):
                found = index
    if found is not None:
        return found
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


def last_messages(events):
    """The last few messages of these events, each clipped, the loop's own ones aside."""
    turns = []
    for event in reversed(events):
        text = message_text(event)
        if text and not text.startswith(FOLLOWUP_MARK):
            role = "user" if getattr(event, "source", "") == "user" else "assistant"
            turns.append(f"{role}: {clip(text, CONTEXT_MESSAGE_CHARS)}")
            if len(turns) == CONTEXT_MESSAGES:
                break
    return "\n\n".join(reversed(turns))


def earlier_context(events, objective):
    """The last few messages before the goal's request."""
    return last_messages(events[:objective_index(events, objective) or 0])


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
        index = objective_index(events, objective)
        words = message_text(events[index]) if index is not None else ""
        request = REQUEST_AND_GOAL.format(request=words, goal=objective) if words and words != objective else objective
        context = last_messages(events[:index or 0])
        if context:
            request = f"{request}\n\n{CONTEXT_HEADER}\n{context}"
        return judge(judge_llm, request, list(events) if index is None else list(events[index:]))

    module.judge_goal = judge_goal
    # The agent gets the owner's own words; the goal is what the UI shows and the judge checks.
    module.GoalController.start = lambda self: getattr(self.objective, "request", "") or self.objective
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


def read_understanding(message):
    """("task", goal) or ("talk", "") from the model's answer (a chat completion message)."""
    for text in [message.get("content"), message.get("reasoning_content")]:
        block = re.search(r"\{.*\}", text or "", re.DOTALL)
        try:
            data = json.loads(block.group(0), strict=False) if block else None  # a line break in a string
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("kind") not in ("task", "talk"):
            continue
        goal = " ".join(str(data.get("goal") or "").split())
        if data["kind"] == "task" and goal:
            return "task", clip(goal, 300)
        return "talk", ""
    raise ValueError("no answer of the expected form")


def recent_messages(conversation):
    """The conversation's last few messages, without reading its whole history."""
    with conversation._state:
        events = conversation._state.events
        tail = [events[index] for index in range(max(0, len(events) - 200), len(events))]
    return last_messages(tail)


async def understand(event_service, text):
    """What the owner's message is, by a short call of the conversation's model without reasoning.
    Any failure is talk: the message then goes the usual way, as before goals."""
    import asyncio
    import httpx
    try:
        conversation = event_service._conversation
        llm = conversation.agent.llm
        context = await asyncio.get_running_loop().run_in_executor(None, recent_messages, conversation)
        user = (f"Conversation before (context only):\n{context}\n\n" if context else "") + f"Owner's newest message:\n{text}"
        model = llm.model.split("/", 1)[1] if llm.model.startswith("openai/") else llm.model
        body = {"model": model, "temperature": 0.3, "max_tokens": 200,
                "messages": [{"role": "system", "content": UNDERSTAND_SYSTEM}, {"role": "user", "content": user}],
                "chat_template_kwargs": {"enable_thinking": False, "reasoning_effort": "none"}}
        key = llm.api_key.get_secret_value() if hasattr(llm.api_key, "get_secret_value") else llm.api_key
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        # trust_env=False: the desktop's proxy settings must not catch a local request.
        async with httpx.AsyncClient(trust_env=False, timeout=UNDERSTAND_SECONDS) as client:
            answer = await client.post(f"{llm.base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
            answer.raise_for_status()
        return read_understanding(answer.json()["choices"][0]["message"])
    except Exception as error:
        print(f"[sdk-patch] goal not understood, sent as a message: {error!r}", file=sys.stderr)
        return "talk", ""


ATTEMPTS = 200  # goal sends remembered for their repeats


def patch_goal_route(module):
    """POST .../goal understands the message first (understand()): a task starts the goal loop with
    the understood goal, talk is sent as a usual message. With "attempt": a repeat of a started or
    starting send gets its outcome and starts nothing; a refused one may be tried again. In memory,
    for the last ATTEMPTS sends.

    Sends to one conversation are understood and delivered in their order: a quick «Остановись»
    understood before a slower request it came after was delivered first, and the old task started
    after the stop. Now the stop comes second and is heard by the running task (nexus_interject.py);
    an addition («и шрифт крупнее») is understood with the request before it in the history."""
    import asyncio
    from collections import OrderedDict, defaultdict
    from uuid import UUID
    from fastapi import Depends, HTTPException, status
    from pydantic import Field
    from openhands.sdk.llm import Message, TextContent

    router = module.conversation_router
    route = next(route for route in router.routes
                 if route.path == router.prefix + "/{conversation_id}/goal" and "POST" in route.methods)
    sends = OrderedDict()
    order = defaultdict(asyncio.Lock)  # by conversation; waiters get it first come, first served

    class StartGoalRequest(module.StartGoalRequest):
        attempt: str | None = Field(default=None, max_length=100,
                                    description="The client's id of this send; a repeat of it starts nothing.")

    async def start(conversation_id, request, conversation_service):
        event_service = await conversation_service.get_event_service(conversation_id)
        if event_service is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        async with order[conversation_id]:
            kind, goal = await understand(event_service, request.objective)
            try:
                if kind == "talk":
                    message = Message(role="user", content=[TextContent(text=request.objective)])
                    await event_service.send_message(message, run=True)
                else:
                    await event_service.start_goal_loop(Goal(goal, request.objective), max_iterations=request.max_iterations)
            except ValueError as error:
                if str(error) in ("conversation_already_running", "goal_already_running"):
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="Conversation run or goal loop already running.")
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error))
        return module.Success()

    async def start_goal_in_conversation(conversation_id: UUID, request: StartGoalRequest,
                                         conversation_service=Depends(module.get_conversation_service)
                                         ) -> module.Success:
        if not request.attempt:
            return await start(conversation_id, request, conversation_service)
        key = (conversation_id, request.attempt)
        if key not in sends:
            sends[key] = asyncio.ensure_future(start(conversation_id, request, conversation_service))
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
