"""Offline contract tests. Run with the agent-server Python and this folder on PYTHONPATH.

No model requests, service restarts or user conversations are needed.
"""
import asyncio
import base64
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sitecustomize as shim
from openhands.sdk import Agent, LLM
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import CondensationSummaryEvent, MessageEvent, UserRejectObservation
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
from openhands.sdk.hooks.executor import HookExecutor
from openhands.sdk.hooks.types import HookEvent
from openhands.sdk.llm import ImageContent, Message, TextContent
from openhands.tools.terminal.definition import TerminalObservation
import openhands.tools.terminal.impl  # Apply the executor patch as on the server.

import nexus_goal as goal
import nexus_interject as interject
import nexus_ledger as ledger
import nexus_screen as screen

WORDS = tempfile.TemporaryDirectory(prefix="nexus-words-test.")
ledger.WORDS_DIR = Path(WORDS.name)  # never the real state folder


class GuardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.hook = HookDefinition(command=shim.GUARD, timeout=10)
        self.event = HookEvent(event_type="PreToolUse", tool_name="terminal",
                               tool_input={"command": "systemctl --user stop ohn-agent"})
        self.executor = HookExecutor(working_dir="/tmp")

    def test_real_guard_blocks_without_executing_the_requested_command(self):
        result = self.executor.execute(self.hook, self.event)
        self.assertFalse(result.should_continue)
        self.assertIn("Страж Nexus", result.reason)

    def test_guard_crash_and_timeout_block(self):
        for result in (subprocess.CompletedProcess([], 1, "", "error"),
                       subprocess.CompletedProcess([], 127, "", "missing"),
                       subprocess.TimeoutExpired("guard", 10)):
            with self.subTest(result=type(result).__name__):
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with patch("openhands.sdk.hooks.executor.subprocess.run", **kwargs):
                    self.assertFalse(self.executor.execute(self.hook, self.event).should_continue)

    def test_unrelated_hook_keeps_sdk_failure_semantics(self):
        with patch("openhands.sdk.hooks.executor.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 1, "", "error")):
            self.assertTrue(self.executor.execute(HookDefinition(command="other-hook"), self.event).should_continue)

    def test_hook_merge_preserves_caller_and_deduplicates_guard(self):
        caller = HookMatcher(matcher="terminal", hooks=[HookDefinition(command="echo ok")])
        config = HookConfig(pre_tool_use=[caller])
        merged = shim.with_guard(shim.with_guard(config))
        self.assertEqual(len(merged.pre_tool_use), 2)
        self.assertTrue(shim.is_guard(merged.pre_tool_use[0].hooks[0].command))
        self.assertEqual(merged.pre_tool_use[1], caller)
        self.assertEqual(config.pre_tool_use, [caller])
        self.assertFalse(shim.is_guard("unterminated '"))

    def test_direct_sdk_conversation_has_guard_without_ui(self):
        with tempfile.TemporaryDirectory(prefix="nexus-sdk-test.") as temp:
            agent = Agent(llm=LLM(model="openai/test", api_key="not-needed", base_url="http://127.0.0.1:1/v1"))
            conversation = LocalConversation(agent=agent, workspace=temp, persistence_dir=temp,
                                             visualizer=None)
            try:
                config = conversation._pending_hook_config
                self.assertTrue(shim.is_guard(config.pre_tool_use[0].hooks[0].command))
                self.assertEqual(config.pre_tool_use[0].matcher, shim.GUARD_TOOLS)
            finally:
                conversation.close()


class SwitchTests(unittest.TestCase):
    def llm(self, usage_id, model="openai/nex25"):
        return LLM(model=model, base_url="http://127.0.0.1:1/v1", api_key="not-needed", usage_id=usage_id)

    def test_quick_switches_before_and_after_the_first_run_keep_the_token_count(self):
        with tempfile.TemporaryDirectory(prefix="nexus-switch-test.") as temp:
            conversation = LocalConversation(agent=Agent(llm=self.llm("default")), workspace=temp,
                                             persistence_dir=temp, visualizer=None)
            try:
                streamed = []
                # As agent-server streams the stats of the LLMs present at start.
                conversation.agent.llm.telemetry.set_stats_update_callback(lambda: streamed.append(1))
                conversation.switch_llm(self.llm("profile:Nex-19G-2080:1", "openai/nex19"))
                conversation.switch_llm(self.llm("profile:Nex-25G:2"))
                stats = conversation._state.stats.usage_to_metrics
                self.assertIn("profile:Nex-19G-2080:1", stats)
                self.assertIs(stats["profile:Nex-25G:2"], conversation.agent.llm.metrics)
                conversation.agent.llm.telemetry._stats_update_callback()
                self.assertTrue(streamed)
                conversation._ensure_agent_ready()
                conversation.switch_llm(self.llm("profile:Tess-27B:3", "openai/tess"))
                self.assertIs(conversation._state.stats.usage_to_metrics["profile:Tess-27B:3"],
                              conversation.agent.llm.metrics)
                self.assertIsNotNone(conversation.agent.llm.telemetry._stats_update_callback)
            finally:
                conversation.close()


class MemoryTests(unittest.TestCase):
    def user(self, text):
        return MessageEvent(source="user", llm_message=Message(role="user", content=[TextContent(text=text)]))

    def test_long_user_constraint_survives_two_condensations(self):
        text = "А" * 3000 + "НЕ УДАЛЯТЬ ДОКУМЕНТЫ" + "Б" * 3000
        first = ledger.build([self.user(text)], 20000)
        self.assertIn(text, first)
        second = ledger.build([CondensationSummaryEvent(summary=first), self.user("Продолжай.")], 20000)
        self.assertIn(text, second)

    def test_rejection_guidance_survives_folding_without_detail_budget(self):
        reason = "Запрещено. " + "А" * 800 + "\nБезопасный способ: сохраните копию."
        event = UserRejectObservation(tool_name="terminal", tool_call_id="call-1",
                                     rejection_reason=reason, rejection_source="hook", action_id="action-1")
        first = ledger._ledger([event], 0, 600, 100)
        second = ledger._ledger([CondensationSummaryEvent(summary=first)], 0, 600, 100)
        self.assertIn(reason.replace("\n", "\n   "), second)

    def test_oversized_user_message_uses_fallback_instead_of_truncation(self):
        self.assertIsNone(ledger.build([self.user("А" * 10000)], 1000))

    def saved(self, block):
        """The words in the file a pinned block points to."""
        path = next(filter(None, map(ledger.SAVED_PATH.match, block.splitlines())))[1]
        self.assertEqual(Path(path).parent, ledger.WORDS_DIR)
        return ledger._quoted(Path(path).read_text(encoding="utf-8"))[0]

    def test_left_out_user_messages_are_whole_counted_saved_and_carried(self):
        words = [f"Сообщение {number}: " + "слово " * (150 if number == 18 else 30) + f"конец {number}."
                 for number in range(1, 21)]
        block = ledger._pinned([self.user(text) for text in words], 6000)
        kept = [text for text in words if text in block]
        # The first one and the newest in a row: an older one never stands in for a too long newer one.
        self.assertEqual(kept, words[:1] + words[18:])
        for number in range(1, 21):  # each message either whole or absent
            self.assertEqual(f"Сообщение {number}:" in block, words[number - 1] in block)
        self.assertIn(ledger._left_out(len(words) - len(kept)), block)
        self.assertEqual(self.saved(block), words)
        self.assertEqual(ledger._quoted(block)[0], words)
        # A ledger takes all the words back from the file; the next block saves them again with the new one.
        folded = ledger.build([CondensationSummaryEvent(summary=block + "\n" + ledger.SUMMARY + "\nСводка.")], 20000)
        for text in words:
            self.assertIn(ledger._quote(text), folded)
        again = ledger._pinned([CondensationSummaryEvent(summary=folded), self.user("Ещё.")], 3000)
        self.assertIn(words[0], again)
        self.assertIn("Ещё.", again)
        self.assertEqual(self.saved(again), words + ["Ещё."])
        shown = [text for text in words + ["Ещё."] if text in again]
        self.assertEqual(sum(map(int, ledger.LEFT_OUT.findall(again))), len(words) + 1 - len(shown))

    def test_a_message_too_long_for_the_block_is_counted_in_its_place(self):
        words = ["Разбери Загрузки.", "Ничего не удаляй.", "\n".join(["строка журнала"] * 800), "Продолжай."]
        block = ledger._pinned([self.user(text) for text in words], 6000)
        lines = block.splitlines()
        self.assertEqual(lines[2:], [ledger._quote(words[0]), ledger._quote(words[1]), ledger._left_out(1),
                                     ledger._quote(words[3])])
        self.assertEqual(ledger._quoted(block)[0], words)

    def test_without_its_file_a_block_carries_what_it_shows_and_counts_the_rest(self):
        words = ["Сообщение 1.", "слово " * 400, "Последнее сообщение."]
        block = ledger._pinned([self.user(text) for text in words], 2000)
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(ledger._quoted(block)[0], [words[0], 1, words[2]])
        with patch.object(ledger, "WORDS_DIR", Path("/proc/nexus-no-such-folder")):
            block = ledger._pinned([self.user(text) for text in words], 2000)
        self.assertIn(ledger.NOT_SAVED, block)
        self.assertEqual(ledger._quoted(block)[0], [words[0], 1, words[2]])

    def test_reasoning_cleanup_only_changes_repeated_long_sentences(self):
        normal = "Проверяю доступное место. Затем изучу журнал ошибок."
        self.assertEqual(shim.unloop(normal), normal)
        sentence = "Сначала необходимо проверить содержимое конкретного файла перед изменением. "
        self.assertEqual(shim.unloop(sentence * 4).count(sentence.strip()), 1)


class PinnedWordsTests(unittest.TestCase):
    """A ban and the current request through condensations of the real patched condenser, with model
    switches; the summarizing model forgets everything the user said."""
    BAN = "Ничего не удаляй в папке Документы, только переноси, и спрашивай меня перед каждым переносом."

    def setUp(self):
        from openhands.sdk.context.condenser import llm_summarizing_condenser as module
        from openhands.sdk.event import SystemPromptEvent
        self.big, self.small = (LLM(model="openai/nex", base_url="http://127.0.0.1:1/v1", api_key="not-needed",
                                    usage_id=usage, max_input_tokens=window)
                                for usage, window in (("big", 224000), ("small", 20000)))
        self.condenser = module.LLMSummarizingCondenser(
            llm=LLM(model="openai/nex", base_url="http://127.0.0.1:1/v1", api_key="not-needed", usage_id="condenser"),
            max_size=12, keep_first=2, max_tokens=160000)
        self.retold = 0

        def generate(llm, messages, **_):
            self.retold += 1
            return SimpleNamespace(id=f"summary-{self.retold}",
                                   message=SimpleNamespace(content=[TextContent(text="Сделано: файлы разобраны.")]))
        async def agenerate(llm, messages, **kwargs):
            return generate(llm, messages, **kwargs)
        self.addCleanup(patch.stopall)
        patch.object(LLM, "generate", generate).start()
        patch.object(LLM, "agenerate", agenerate).start()
        patch.object(module, "get_total_token_count", lambda *_: 0).start()
        self.events = [SystemPromptEvent(system_prompt=TextContent(text="Ты агент."), tools=[]),
                       MemoryTests.user(None, "Разбери папку Загрузки по типам файлов.")]

    def say(self, *texts):
        self.events += [MemoryTests.user(None, text) for text in texts]

    def work(self, steps, answer="Перенесла"):
        self.events += [MessageEvent(source="agent", llm_message=Message(
            role="assistant", content=[TextContent(text=f"{answer} файл {number}.")])) for number in range(steps)]

    def condense(self, llm, hard=False, run_async=False):
        from openhands.sdk.context.view import View
        view = View.from_events(self.events)
        if run_async:  # as the agent's own step calls it
            condensation = asyncio.run(self.condenser.ahard_context_reset(view, agent_llm=llm) if hard
                                       else self.condenser.aget_condensation(view, agent_llm=llm))
        else:
            condensation = (self.condenser.hard_context_reset(view, agent_llm=llm) if hard
                            else self.condenser.get_condensation(view, agent_llm=llm))
        self.events.append(condensation)
        return condensation.summary

    def test_ban_survives_ledgers_model_summaries_and_model_switches(self):
        log = "строка журнала\n" * 800
        self.say(self.BAN)
        self.work(12)
        first = self.condense(self.big)  # a ledger
        self.assertTrue(first.startswith(ledger.HEADER))
        # The small model: a pasted log does not fit its ledger; the model retells.
        self.say(log, "Продолжай.")
        self.work(12, "Перенесла последний")
        second = self.condense(self.small)
        self.assertEqual(self.retold, 1)
        self.assertTrue(second.startswith(ledger.PINNED))
        self.assertIn(self.BAN, second)
        self.assertIn("Продолжай.", second)
        self.assertNotIn(log, second)
        self.assertIn(ledger._left_out(1), second)
        self.assertIn("Перенесла последний файл", second.partition(ledger.REPLY)[2].partition(ledger.SUMMARY)[0])
        self.assertTrue(second.endswith("Сделано: файлы разобраны."))
        # Back to the big model: its ledger takes all the words back as USER steps, the log from the file.
        self.say("Теперь картинки.")
        self.work(12)
        third = self.condense(self.big)
        self.assertEqual(self.retold, 1)
        self.assertIn("USER: " + self.BAN, third)
        self.assertIn(ledger._quote(log.strip()), third)
        self.assertNotIn(ledger._left_out(1), third)
        # Out of room on the small model: everything after the system prompt is retold.
        self.say("Стоп, сначала покажи список.")
        self.work(12)
        fourth = self.condense(self.small, hard=True)
        self.assertEqual(self.retold, 2)
        for words in ("Разбери папку Загрузки по типам файлов.", self.BAN, "Стоп, сначала покажи список."):
            self.assertIn("USER: " + words, fourth)
        from openhands.sdk.context.view import View
        view = View.from_events(self.events)
        self.assertEqual(len(view.events), 2)
        self.assertIn(self.BAN, view.events[1].summary)

    def test_the_checks_follow_up_is_no_word_of_the_user(self):
        followup = goal.FOLLOWUP_PROMPT.format(iteration=1, missing="Не настроен постоянный фоновый мониторинг")
        self.say(self.BAN, followup)
        self.work(12)
        first = self.condense(self.big)
        self.assertIn(ledger.CHECK + "Проверка Nexus: задача ещё не выполнена", first)
        self.assertNotIn("USER: " + goal.FOLLOWUP_MARK, first)
        pinned = ledger._pinned([MemoryTests.user(None, self.BAN), MemoryTests.user(None, followup)], 20000)
        self.assertIn(self.BAN, pinned)
        self.assertNotIn("мониторинг", pinned)
        # A block written before keeps it as the user's words: taken back, it is not one any more.
        old = "\n".join([ledger.PINNED, ledger._quote(self.BAN), ledger._quote(followup)])
        self.assertEqual(ledger._quoted(old)[0], [self.BAN])
        old_ledger = "\n".join([ledger.HEADER, "#1 " + ledger._quote(self.BAN), "#2 " + ledger._quote(followup)])
        rebuilt = ledger.build([CondensationSummaryEvent(summary=old_ledger), MemoryTests.user(None, "Дальше.")], 160000)
        self.assertIn("#2 " + ledger.CHECK + goal.FOLLOWUP_MARK, rebuilt)
        self.assertIn("#1 USER: " + self.BAN, rebuilt)

    def test_long_first_request_is_never_cut_and_its_ban_stays_reachable(self):
        # The acceptance case: a 50 061-character first request with a ban in its middle, a 224K model.
        ban = "НИКОГДА НЕ УДАЛЯЙ МОИ ФОТОГРАФИИ."
        request = "План работы. " + "А" * 25000 + ban + "Б" * 25000 + " Конец просьбы."
        self.events[1:] = [MemoryTests.user(None, request)]
        self.work(3)
        tess = LLM(model="openai/tess", base_url="http://127.0.0.1:1/v1", api_key="not-needed", usage_id="tess",
                   max_input_tokens=229376)
        summary = self.condense(tess, hard=True, run_async=True)
        words = summary.partition(ledger.REPLY)[0]
        self.assertNotIn("План работы", words)  # whole or not at all
        self.assertIn(ledger._left_out(1), words)
        self.assertEqual(MemoryTests.saved(self, summary), [request])
        # When the block itself is condensed, the ledger takes the request back whole.
        self.assertIn(ledger._quote(request), ledger.build([CondensationSummaryEvent(summary=summary)], 160000))

    def test_async_condensations_pin_the_words_too(self):
        self.say(self.BAN, "строка журнала\n" * 800, "Продолжай.")
        self.work(12)
        second = self.condense(self.small, run_async=True)
        self.assertTrue(second.startswith(ledger.PINNED))
        self.assertIn("USER: " + self.BAN, second)
        self.work(12)
        third = self.condense(self.small, hard=True, run_async=True)
        self.assertEqual(self.retold, 2)
        self.assertIn("USER: " + self.BAN, third)
        self.assertIn(ledger._left_out(1), third)


class ScreenTests(unittest.TestCase):
    def test_image_reaches_llm_and_is_resized(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix="nexus-screen-test.") as temp:
            path = Path(temp) / "screen.png"
            Image.new("RGB", (2400, 1200), "white").save(path)
            observation = TerminalObservation(command="screenshot", content=[TextContent(text=f"@@attach {path}")])
            result = screen.attach(observation)
            images = [part for part in result.to_llm_content if isinstance(part, ImageContent)]
            self.assertEqual(len(images), 1)
            raw = base64.b64decode(images[0].image_urls[0].split(",", 1)[1])
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.size, (1920, 960))


class GoalTests(unittest.TestCase):
    objective = "Создай файл hello.txt"

    def user(self, text):
        return MessageEvent(source="user", llm_message=Message(role="user", content=[TextContent(text=text)]))

    def run_events(self, output):
        from openhands.sdk.event import ActionEvent, ObservationEvent
        from openhands.sdk.llm import MessageToolCall
        from openhands.tools.terminal.definition import TerminalAction
        call = MessageToolCall(id="call-1", name="terminal", arguments='{"command": "echo привет > hello.txt"}',
                               origin="completion")
        action = ActionEvent(thought=[TextContent(text="Создаю файл.")], action=TerminalAction(command="echo привет > hello.txt"),
                             tool_name="terminal", tool_call_id="call-1", tool_call=call, llm_response_id="r1")
        observation = ObservationEvent(observation=TerminalObservation(command="echo", content=[TextContent(text=output)]),
                                       action_id=action.id, tool_name="terminal", tool_call_id="call-1")
        return [self.user("старая просьба"), self.user(self.objective), action, observation]

    def judge_llm(self, reply):
        class Response:
            message = Message(role="assistant", content=[TextContent(text=reply)])

        class FakeLLM:
            stream = False
            prompts = []

            def completion(self, messages):
                self.prompts.append(messages)
                return Response()
        return FakeLLM()

    def test_transcript_has_commands_clipped_outputs_and_starts_at_the_goal(self):
        run = self.run_events("Х" * 10000)
        events = run[goal.objective_index(run, self.objective):]
        text = goal.render_transcript(events)
        self.assertNotIn("старая просьба", text)
        self.assertIn("echo привет > hello.txt", text)
        self.assertIn("пропущено 7000 символов", text)
        self.assertLess(len(goal.render_transcript(self.run_events("Х" * 10000) * 100)), goal.TRANSCRIPT_CHARS + 200)

    def test_owner_decision_stops_the_loop_and_plain_gap_continues_in_russian(self):
        from openhands.sdk.conversation.goal import controller as sdk
        from openhands.agent_server import event_service
        stop = sdk.GoalController(self.objective, self.judge_llm(
            '{"score": 0.3, "complete": false, "missing": "выбрать папку", "needs_user": true}'))
        step = stop.on_run_finished(self.run_events("ok"))
        self.assertIsInstance(step, sdk.GoalDone)
        self.assertEqual(step.outcome.status, "capped")
        self.assertEqual(step.outcome.verdict.missing, goal.NEEDS_USER + "выбрать папку")
        llm = self.judge_llm('{"score": 0.5, "complete": false, "missing": "нет проверки файла"}')
        step = sdk.GoalController(self.objective, llm).on_run_finished(self.run_events("ok"))
        self.assertIsInstance(step, sdk.GoalContinue)
        self.assertTrue(step.followup.startswith(goal.FOLLOWUP_MARK))
        self.assertIn("нет проверки файла", step.followup)
        system, user = (message.content[0].text for message in llm.prompts[0])
        self.assertIn("not a programmer", system)
        # The earlier request comes as context with the objective, not as part of the judged run.
        request, transcript = user.split("<transcript>")
        self.assertIn(goal.CONTEXT_HEADER + "\nuser: старая просьба", request)
        self.assertNotIn("старая просьба", transcript)
        self.assertTrue(event_service.RESUME_PROMPT.startswith(goal.FOLLOWUP_MARK))

    def test_verdict_is_complete_only_as_json_true_with_a_matching_score(self):
        from openhands.sdk.conversation.goal import controller as sdk, judge

        def verdict(text):
            return judge._parse_verdict(Message(role="assistant", content=[TextContent(text=text)]))
        for text in ['{"score": 0.95, "complete": true, "missing": ""}', '{"score": 1, "complete": true}',
                     'Вот вердикт: {"score": 5, "complete": true}']:
            self.assertTrue(verdict(text).complete, text)
        for text, why in [('{"score": 0.9, "complete": "true"}', "не по форме"),
                          ('{"score": 0.2, "complete": "false", "missing": "нет файла"}', "нет файла; проверка ответила не по форме"),
                          ('{"score": 0.9}', "не по форме"),
                          ('{"score": 0.9, "complete": 1}', "не по форме"),
                          ('{"score": 0.3, "complete": true}', "противоречит себе: «готово», но уверенность 30%"),
                          ('{"score": "0.9", "complete": true}', "уверенность 0%"),
                          ('{"score": NaN, "complete": true}', "уверенность 0%"),
                          ('{"score": true, "complete": true}', "уверенность 0%"),
                          ('{"score": 0.9, "complete": false}', "проверка не назвала"),
                          ('{"score": 0.9, "complete": tru', "не смогла прочитать"),
                          ("не JSON", "не смогла прочитать"),
                          ('{"score": 0.9, "complete": true, "needs_user": true, "missing": "выбрать папку"}',
                           goal.NEEDS_USER + "выбрать папку")]:
            result = verdict(text)
            self.assertFalse(result.complete, text)
            self.assertIn(why, result.missing, text)
        # The acceptance case through the real controller: a "false" string with needs_user is no success.
        step = sdk.GoalController(self.objective, self.judge_llm(
            '{"score": 0.2, "complete": "false", "missing": "Файл результата не создан", "needs_user": true}'
        )).on_run_finished(self.run_events("ok"))
        self.assertIsInstance(step, sdk.GoalDone)
        self.assertEqual(step.outcome.status, "capped")
        self.assertFalse(step.outcome.verdict.complete)
        step = sdk.GoalController(self.objective, self.judge_llm('{"score": 0.2, "complete": "false"}')).on_run_finished([])
        self.assertIsInstance(step, sdk.GoalContinue)


    def status(self, objective, iteration=0):
        from openhands.sdk.event import ConversationStateUpdateEvent
        return ConversationStateUpdateEvent(key="goal", value={
            "active": True, "status": "running", "iteration": iteration, "max_iterations": 3, "objective": objective})

    def test_understood_goal_is_judged_with_the_owners_words_which_the_agent_gets(self):
        from openhands.sdk.conversation.goal import controller as sdk
        words, understood = "сделай файлик с приветом", "Файл hello.txt с текстом «привет» создан"
        events = self.run_events("ok")
        events[1:2] = [self.status(understood), self.user(words)]
        llm = self.judge_llm('{"score": 0.5, "complete": false, "missing": "нет проверки"}')
        controller = sdk.GoalController(goal.Goal(understood, words), llm)
        self.assertEqual(controller.start(), words)
        controller.on_run_finished(events)
        # After a restart the goal is a plain string again (from its status) and finds the same words.
        sdk.GoalController(understood, llm).on_run_finished(events + [self.status(understood, 1),
                                                                       self.user(goal.FOLLOWUP_MARK + " ещё")])
        for _, user in (prompt for prompt in llm.prompts):
            request, transcript = user.content[0].text.split("<transcript>")
            self.assertIn(words, request)
            self.assertIn(understood, request)
            self.assertIn(goal.CONTEXT_HEADER + "\nuser: старая просьба", request)
            self.assertNotIn("старая просьба", transcript)
        self.assertIn("not requirements", llm.prompts[0][0].content[0].text)
        self.assertEqual(sdk.GoalController(self.objective, llm).start(), self.objective)

    def test_understanding_answer_is_read_strictly(self):
        read = goal.read_understanding
        self.assertEqual(read({"content": '{"kind": "task", "goal": " Звук\n работает "}'}), ("task", "Звук работает"))
        self.assertEqual(read({"content": "", "reasoning_content": 'ответ: {"kind": "talk", "goal": ""}'}), ("talk", ""))
        self.assertEqual(read({"content": '{"kind": "task", "goal": ""}'}), ("talk", ""))
        for message in [{"content": "не JSON"}, {"content": '{"kind": "maybe"}'}, {}]:
            with self.assertRaises(ValueError):
                read(message)

    def test_understanding_failure_sends_the_message_as_usual(self):
        self.assertEqual(asyncio.run(goal.understand(SimpleNamespace(), "Почини звук")), ("talk", ""))


class InterjectTests(unittest.TestCase):
    """nexus_interject on stand-ins of the conversation and the agent with the same method contracts."""

    def setUp(self):
        test = self
        self.calls, self.release = [], None

        class Conversation:
            def __init__(self):
                self._state = SimpleNamespace(_lock=SimpleNamespace(owned=lambda: True), execution_status="running",
                                              last_user_message_id=None, active_branch=lambda limit=None: [])
                self.messages = []

            @contextlib.asynccontextmanager
            async def _released_state_lock_during_io(self):
                yield

            def send_message(self, message, sender=None):
                self.messages.append(message)
                self._state.last_user_message_id = len(self.messages)

        class Agent:
            async def astep(self, conversation, on_event, on_token=None):
                test.calls.append(list(conversation.messages))
                if test.spoke_first:
                    on_event(test.event)
                async with conversation._released_state_lock_during_io():
                    test.release = asyncio.Event()
                    await test.release.wait()
                on_event(test.event)

        interject.patch_conversation(SimpleNamespace(LocalConversation=Conversation))
        interject.patch_agent(SimpleNamespace(Agent=Agent))
        self.conversation, self.agent, self.spoke_first = Conversation(), Agent(), False
        self.event = MessageEvent(source="agent", llm_message=Message(role="assistant", content=[TextContent(text="шаг")]))

    def step(self, during):
        """One step; `during` runs while it waits for the model."""
        events = []

        async def run():
            task = asyncio.create_task(self.agent.astep(self.conversation, events.append))
            while self.release is None:
                await asyncio.sleep(0.01)
            first, self.release = self.release, None
            await during(task)
            await asyncio.sleep(0.05)
            (self.release or first).set()
            await task
        asyncio.run(run())
        return events

    def message_from_another_thread(self, text):
        async def during(task):
            await asyncio.get_running_loop().run_in_executor(None, self.conversation.send_message, text)
        return during

    def test_a_message_during_the_answer_starts_the_step_again_with_it(self):
        events = self.step(self.message_from_another_thread("Остановись"))
        self.assertEqual(self.calls, [[], ["Остановись"]])
        self.assertEqual(events, [self.event])

    def test_two_quick_corrections_start_the_step_again_once_with_both(self):
        async def during(task):  # both are heard before the step sees the first cancel
            self.conversation.send_message("Сделай шрифт крупнее")
            self.conversation.send_message("И оставь тёмную тему")
        events = self.step(during)
        self.assertEqual(self.calls, [[], ["Сделай шрифт крупнее", "И оставь тёмную тему"]])
        self.assertEqual(events, [self.event])

    def test_after_the_step_recorded_something_it_ends_as_usual(self):
        self.spoke_first = True
        events = self.step(self.message_from_another_thread("Остановись"))
        self.assertEqual(self.calls, [[]])
        self.assertEqual(len(events), 2)

    def test_the_stop_button_still_stops_the_run(self):
        async def stop(task):
            self.conversation._cancel_token = SimpleNamespace(is_cancelled=True)
            self.conversation.send_message("и ещё")
            await asyncio.sleep(0.02)
            task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            self.step(stop)
        self.assertEqual(len(self.calls), 1)

    def test_after_finish_or_an_answer_the_step_ends_without_the_model(self):
        from openhands.sdk.event import ObservationEvent
        from openhands.sdk.tool.builtins.finish import FinishObservation, FinishTool
        finish = ObservationEvent(source="environment", tool_name=FinishTool.name, tool_call_id="c1",
                                  action_id="a1", observation=FinishObservation.from_text("готово"))
        heard = MessageEvent(source="user", llm_message=Message(role="user", content=[TextContent(text="ещё")]))
        for history, asks in (([finish], False), ([self.event], False), ([self.event, heard], True)):
            self.calls.clear()
            self.conversation._state.execution_status = "running"
            self.conversation._state.active_branch = lambda limit=None, history=history: history
            if asks:
                self.step(lambda task: asyncio.sleep(0))
            else:
                asyncio.run(self.agent.astep(self.conversation, lambda event: None))
                self.assertEqual(self.conversation._state.execution_status, "finished")
            self.assertEqual(len(self.calls), int(asks))


class InterjectRunTests(unittest.TestCase):
    """The real run loop with the patched agent; the model is a stand-in that refuses a request
    ending in the agent's own answer, as llama-server with thinking on does (prefill)."""

    def test_the_heard_message_is_answered_once_without_an_empty_extra_step(self):
        from litellm import ModelResponse
        from openhands.sdk.conversation.state import ConversationExecutionStatus
        from openhands.sdk.llm import LLMResponse
        asked = []

        async def agenerate(llm, messages, **_):
            asked.append(messages[-1])
            if len(asked) == 1:  # the owner speaks while the model answers
                await asyncio.get_running_loop().run_in_executor(None, conversation.send_message, "Остановись")
                await asyncio.sleep(10)
            if messages[-1].role == "assistant":
                raise RuntimeError("Assistant response prefill is incompatible with enable_thinking.")
            return LLMResponse(message=Message(role="assistant", content=[TextContent(text="Остановилась.")]),
                               metrics=llm.metrics.get_snapshot(), raw_response=ModelResponse())

        with tempfile.TemporaryDirectory(prefix="nexus-interject-test.") as temp, \
                patch.object(LLM, "agenerate", agenerate):
            agent = Agent(llm=LLM(model="openai/tess", base_url="http://127.0.0.1:1/v1", api_key="not-needed"))
            conversation = LocalConversation(agent=agent, workspace=temp, persistence_dir=temp, visualizer=None)
            try:
                conversation.send_message("Проверь место на диске")
                asyncio.run(asyncio.wait_for(conversation.arun(), 30))
                self.assertEqual(len(asked), 2)
                self.assertIn("Остановись", str(asked[1].content))  # the redone request reads it
                self.assertEqual(conversation._state.execution_status, ConversationExecutionStatus.FINISHED)
                answers = [event for event in conversation._state.events
                           if isinstance(event, MessageEvent) and event.source == "agent"]
                self.assertEqual(len(answers), 1)
            finally:
                conversation.close()

    def test_a_message_that_comes_with_the_answer_is_heard_once(self):
        """Too late for the cancel: the answer is already back when the message lands."""
        from litellm import ModelResponse
        from openhands.sdk.conversation.state import ConversationExecutionStatus
        from openhands.sdk.llm import LLMResponse
        asked = []

        async def agenerate(llm, messages, **_):
            asked.append(messages[-1])
            if len(asked) == 1:
                conversation.send_message("Остановись")
            else:
                await asyncio.sleep(0.05)  # the late hear() runs during this request
            if messages[-1].role == "assistant":
                raise RuntimeError("Assistant response prefill is incompatible with enable_thinking.")
            return LLMResponse(message=Message(role="assistant", content=[TextContent(text="Остановилась.")]),
                               metrics=llm.metrics.get_snapshot(), raw_response=ModelResponse())

        with tempfile.TemporaryDirectory(prefix="nexus-interject-test.") as temp, \
                patch.object(LLM, "agenerate", agenerate):
            agent = Agent(llm=LLM(model="openai/tess", base_url="http://127.0.0.1:1/v1", api_key="not-needed"))
            conversation = LocalConversation(agent=agent, workspace=temp, persistence_dir=temp, visualizer=None)
            try:
                conversation.send_message("Проверь место на диске")
                asyncio.run(asyncio.wait_for(conversation.arun(), 30))
                self.assertEqual(len(asked), 2)
                self.assertIn("Остановись", str(asked[1].content))
                self.assertEqual(conversation._state.execution_status, ConversationExecutionStatus.FINISHED)
            finally:
                conversation.close()


class GoalCorrectionTests(unittest.TestCase):
    """A message during a goal: a correction keeps the goal and its judge, a stop ends it as in the SDK."""

    def deliver(self, text):
        """(the goal was stopped, the message reached the conversation)"""
        from openhands.agent_server.event_service import EventService
        stopped, received = [], []

        async def run():
            loop = asyncio.create_task(asyncio.sleep(10))

            async def stop_goal_loop():
                stopped.append(text)
                loop.cancel()
                return True
            service = SimpleNamespace(_conversation=SimpleNamespace(send_message=received.append), _goal_loop_task=loop,
                                      stop_goal_loop=stop_goal_loop, _explicit_interrupt_generation=0)
            await EventService.send_message(service, Message(role="user", content=[TextContent(text=text)]))
            loop.cancel()
        asyncio.run(run())
        return bool(stopped), len(received)

    def test_a_correction_keeps_the_goal_a_stop_ends_it(self):
        for text in ["И шрифт покрупнее", "И оставь тёмную тему", "Спасибо, продолжай"]:
            self.assertEqual(self.deliver(text), (False, 1), text)
        for text in ["Стоп", "Остановись, пожалуйста", "Подожди минутку", "Хватит", "Не надо больше ничего делать"]:
            self.assertEqual(self.deliver(text), (True, 1), text)

    def test_the_judge_reads_the_correction_as_the_owners_and_the_follow_up_as_its_own(self):
        events = [GoalTests.user(None, "Сделай тёмную тему"), GoalTests.user(None, "И шрифт покрупнее"),
                  GoalTests.user(None, goal.FOLLOWUP_PROMPT.format(iteration=1, missing="нет проверки"))]
        transcript = goal.render_transcript(events)
        self.assertIn("user: И шрифт покрупнее", transcript)
        self.assertIn(f"{goal.CHECK_ROLE}: {goal.FOLLOWUP_MARK}", transcript)
        self.assertNotIn(f"user: {goal.FOLLOWUP_MARK}", transcript)
        self.assertIn("correcting or adding to the request", goal.JUDGE_CONTEXT)


class GoalSendTests(unittest.TestCase):
    """POST /api/conversations/{id}/goal with the UI's attempt id, through the patched route of the
    real router; only the conversation's event service is a fake."""

    def setUp(self):
        from fastapi import FastAPI
        from openhands.agent_server import conversation_router as module
        from openhands.agent_server.dependencies import get_conversation_service
        self.started, self.sent, self.log, self.busy, test = [], [], [], False, self
        self.kind = "task"

        async def understand(event_service, text):
            return (test.kind, f"Цель: {text}" if test.kind == "task" else "")
        understanding = patch.object(goal, "understand", understand)
        understanding.start()
        self.addCleanup(understanding.stop)

        class Events:
            async def send_message(self, message, run=False):
                test.sent.append((message.content[0].text, run))
                test.log.append(message.content[0].text)

            async def start_goal_loop(self, objective, max_iterations=10):
                await asyncio.sleep(0.05)
                if test.busy:
                    raise ValueError("goal_already_running")
                test.busy = True
                test.started.append(objective)
                test.log.append(objective)

        class Service:
            async def get_event_service(self, conversation_id):
                return Events()
        self.app = FastAPI()
        self.app.include_router(module.conversation_router, prefix="/api")
        self.app.dependency_overrides[get_conversation_service] = lambda: Service()

    def send(self, *bodies, conversation="7f6b8a4e-0000-4000-8000-000000000001"):
        """The bodies sent at once; their answer codes."""
        import httpx

        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                answers = await asyncio.gather(*(client.post(f"/api/conversations/{conversation}/goal", json=body)
                                                 for body in bodies))
            return [answer.status_code for answer in answers]
        return asyncio.run(run())

    def test_a_repeated_send_starts_the_goal_once(self):
        body = {"objective": "Создай файл", "max_iterations": 3, "attempt": "a1"}
        self.assertEqual(self.send(body, body), [200, 200])  # the repeat while the first one starts
        self.assertEqual(self.send(body), [200])  # and after it
        self.assertEqual(self.started, ["Цель: Создай файл"])
        self.assertEqual(self.started[0].request, "Создай файл")
        # Another send of the same text is a new request: the goal runs, so it is refused.
        self.assertEqual(self.send({**body, "attempt": "a2"}), [409])
        self.assertEqual(self.send({"objective": "Создай файл"}), [409])
        # The same id in another conversation is another send.
        self.busy = False
        self.assertEqual(self.send(body, conversation="7f6b8a4e-0000-4000-8000-000000000002"), [200])
        self.assertEqual(len(self.started), 2)

    def test_a_refused_send_may_be_tried_again(self):
        self.busy = True
        body = {"objective": "Создай файл", "attempt": "b1"}
        self.assertEqual(self.send(body), [409])
        self.busy = False
        self.assertEqual(self.send(body), [200])
        self.assertEqual(self.started, ["Цель: Создай файл"])

    def test_a_later_message_waits_for_the_earlier_one_to_be_understood(self):
        # «Почини звук» is understood slowly, «Остановись» at once: the stop must still come after it.
        async def understand(event_service, text):
            await asyncio.sleep(0.3 if text == "Почини звук" else 0)
            return ("task", f"Цель: {text}") if text == "Почини звук" else ("talk", "")
        with patch.object(goal, "understand", understand):
            import httpx

            async def run():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                    url = "/api/conversations/7f6b8a4e-0000-4000-8000-000000000001/goal"
                    first = asyncio.ensure_future(client.post(url, json={"objective": "Почини звук", "attempt": "d1"}))
                    await asyncio.sleep(0.05)
                    second = await client.post(url, json={"objective": "Остановись", "attempt": "d2"})
                    return [(await first).status_code, second.status_code]
            self.assertEqual(asyncio.run(run()), [200, 200])
        self.assertEqual(self.log, ["Цель: Почини звук", "Остановись"])

    def test_talk_goes_as_a_usual_message_without_a_goal(self):
        self.kind = "talk"
        body = {"objective": "Спасибо, всё работает", "attempt": "c1"}
        self.assertEqual(self.send(body, body), [200, 200])
        self.assertEqual(self.sent, [("Спасибо, всё работает", True)])
        self.assertEqual(self.started, [])


if __name__ == "__main__":
    unittest.main()
