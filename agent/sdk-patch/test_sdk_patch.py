"""Offline contract tests. Run with the agent-server Python and this folder on PYTHONPATH.

No model requests, service restarts or user conversations are needed.
"""
import asyncio
import base64
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
import nexus_ledger as ledger
import nexus_screen as screen


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

    def test_left_out_user_messages_are_whole_counted_and_carried(self):
        words = [f"Сообщение {number}: " + "слово " * (300 if number == 18 else 30) + f"конец {number}."
                 for number in range(1, 21)]
        block = ledger._pinned([self.user(text) for text in words], 6000)
        kept = [text for text in words if text in block]
        # The first one and the newest in a row: an older one never stands in for a too long newer one.
        self.assertEqual(kept, words[:1] + words[18:])
        for number in range(1, 21):  # each message either whole or absent
            self.assertEqual(f"Сообщение {number}:" in block, words[number - 1] in block)
        self.assertIn(ledger._left_out(len(words) - len(kept)), block)
        # A ledger takes the words back; the next pinned block still counts the left-out ones.
        folded = ledger.build([CondensationSummaryEvent(summary=block + "\n" + ledger.SUMMARY + "\nСводка.")], 20000)
        again = ledger._pinned([CondensationSummaryEvent(summary=folded), self.user("Ещё.")], 2000)
        self.assertIn(words[0], again)
        self.assertIn("Ещё.", again)
        self.assertEqual(sum(map(int, ledger.LEFT_OUT.findall(again))), len(words) - len(kept) + sum(
            text not in again for text in kept[1:]))

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
        # Back to the big model: its ledger takes the words back as USER steps.
        self.say("Теперь картинки.")
        self.work(12)
        third = self.condense(self.big)
        self.assertEqual(self.retold, 1)
        self.assertIn("USER: " + self.BAN, third)
        self.assertIn(ledger._left_out(1), third)
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
        events = goal.since_objective(self.run_events("Х" * 10000), self.objective)
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

if __name__ == "__main__":
    unittest.main()
