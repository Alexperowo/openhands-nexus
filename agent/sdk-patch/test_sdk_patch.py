"""Offline contract tests. Run with the agent-server Python and this folder on PYTHONPATH.

No model requests, service restarts or user conversations are needed.
"""
import base64
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
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

    def test_reasoning_cleanup_only_changes_repeated_long_sentences(self):
        normal = "Проверяю доступное место. Затем изучу журнал ошибок."
        self.assertEqual(shim.unloop(normal), normal)
        sentence = "Сначала необходимо проверить содержимое конкретного файла перед изменением. "
        self.assertEqual(shim.unloop(sentence * 4).count(sentence.strip()), 1)


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


if __name__ == "__main__":
    unittest.main()
