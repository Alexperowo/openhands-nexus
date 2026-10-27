"""agent-server loads this through PYTHONPATH (launcher/run.sh agent): SDK fixes until a release has them.

agent-server 1.58 (still in main) sends a model its earlier reasoning back only for a fixed list
of cloud models and ignores capability_overrides for it, so the local models saw each earlier
step with an empty <think> block although their templates expect the text there (the Tess card:
keep preserve_thinking on in agent loops). This honours capability_overrides
["send_reasoning_content"] from agent/config/profiles.json. Upstream: PR
OpenHands/software-agent-sdk#4446 adds exactly this override.

A model or reasoning switch (switch_llm) also lost the conversation's token count: the new LLM
streams no stats (only the LLMs present at start got the callback), and one switched in before
the first run after a restart is never added to the stats at all (#5639, fix in PR #5667).
The context meter then said "no data yet". Drop each fix once a release has it.

A step whose reasoning looped (the same sentences over and over until the thinking budget) went
back to the model in every later request, and the model kept looping on it. Only what is sent
is cleaned, the same way every time so the prompt cache still matches; the conversation's
events keep the original. Ours, not an upstream bug.

The conversation condenser keeps a ledger of the forgotten steps instead of the model's retelling
and starts at 70% of each model's window: nexus_ledger.py.

The desktop commands' `@@attach <image>` lines become images of the terminal result, as in the
harness Holo4 is trained with: nexus_screen.py.

Every conversation gets the guard (guard/guard.py) as its first PreToolUse hook. The UI adds it to
each start request it sends, but scheduled tasks (automation) and scripts start conversations
through the API with hook configs of their own, and their agent ran unguarded. Ours, not an
upstream bug.

A message the owner sends while the model answers is heard at once instead of after the answer it
came during: nexus_interject.py.
"""
import dataclasses
import os
import inspect
import re
import shlex
import sys
from collections import Counter
from importlib.machinery import PathFinder

HERE = os.path.dirname(os.path.abspath(__file__))

# Programs the agent runs inherit this environment: keep their Python free of this file.
_rest = [part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep)
         if part and os.path.abspath(part) != HERE]
if _rest:
    os.environ["PYTHONPATH"] = os.pathsep.join(_rest)
else:
    os.environ.pop("PYTHONPATH", None)


def patch_llm(module):
    original = module.LLM._model_features

    def _model_features(self):
        features = original(self)
        wanted = (self.capability_overrides or {}).get("send_reasoning_content")
        if isinstance(wanted, bool) and wanted != features.send_reasoning_content:
            features = dataclasses.replace(features, send_reasoning_content=wanted)
        return features

    module.LLM._model_features = _model_features


# The same hook the UI adds (ui/src/guard-hooks.ts, ui/vite.config.ts).
GUARD = "/usr/bin/python3 -I " + shlex.quote(os.path.join(os.path.dirname(os.path.dirname(HERE)), "guard", "guard.py"))
GUARD_TOOLS = "terminal|file_editor|planning_file_editor"


def is_guard(command):
    try:
        return shlex.split(command or "") == shlex.split(GUARD)
    except ValueError:
        return False


def patch_hook_executor(module):
    """SDK hooks normally fail open; failure of the Nexus safety hook must block."""
    original = module.HookExecutor.execute

    def execute(self, hook, event, env=None):
        result = original(self, hook, event, env=env)
        if is_guard(hook.command) and not result.success and result.should_continue:
            return result.model_copy(update={"blocked": True,
                "reason": "Страж Nexus: проверка команды не завершилась. Действие не выполнено; "
                          "разбей команду на простые шаги. Если ошибка повторится, сообщи о сбое стража."})
        return result

    module.HookExecutor.execute = execute


def with_guard(config):
    """The guard first, then the caller's hooks without another copy of it (any quoting)."""
    from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
    guard = HookMatcher(matcher=GUARD_TOOLS, hooks=[HookDefinition(command=GUARD, timeout=10)])
    if config is None:
        return HookConfig(pre_tool_use=[guard])
    others = [matcher for matcher in config.pre_tool_use
              if not (matcher.hooks and all(is_guard(hook.command) for hook in matcher.hooks))]
    return config.model_copy(update={"pre_tool_use": [guard, *others]})


def patch_conversation(module):
    from openhands.sdk.llm.llm_registry import RegistryEvent
    init = module.LocalConversation.__init__
    signature = inspect.signature(init)

    def __init__(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.arguments["hook_config"] = with_guard(bound.arguments.get("hook_config"))
        init(*bound.args, **bound.kwargs)

    module.LocalConversation.__init__ = __init__
    original = module.LocalConversation.switch_llm

    def switch_llm(self, llm):
        streaming = self.agent.llm.telemetry._stats_update_callback
        original(self, llm)
        new_llm = self.agent.llm
        # Adds it when the stats missed it; for one already counted it changes nothing.
        self._state.stats.register_llm(RegistryEvent(llm=new_llm))
        if streaming is not None and new_llm.telemetry._stats_update_callback is None:
            new_llm.telemetry.set_stats_update_callback(streaming)

    module.LocalConversation.switch_llm = switch_llm
    try:
        import nexus_interject
        nexus_interject.patch_conversation(module)
    except Exception as error:  # not a safety fix: the server starts without it
        print(f"[sdk-patch] new message during an answer not applied: {error!r}", file=sys.stderr)


def patch_agent(module):
    import nexus_interject
    nexus_interject.patch_agent(module)


# Sentences and lines with what separates them; split() keeps the separators at odd places.
_PIECES = re.compile(r"((?<=[.!?…])[ \t]+|\n+)")


def unloop(reasoning):
    """Reasoning with a long sentence 3+ times is a loop: keep each sentence only once."""
    parts = _PIECES.split(reasoning)
    pieces, gaps = parts[0::2], parts[1::2] + [""]
    keys = [" ".join(piece.split()).lower() for piece in pieces]
    counts = Counter(key for key in keys if len(key) >= 40)
    if not counts or max(counts.values()) < 3:
        return reasoning
    seen, kept, dropped = set(), [], 0
    for piece, gap, key in zip(pieces, gaps, keys):
        if len(key) >= 8 and key in seen:  # short ones ("Но это сложно.") repeat in loops too
            dropped += 1
            continue
        seen.add(key)
        kept.append(piece + gap)
    return ("".join(kept).rstrip()
            + f"\n\n[Nexus: this reasoning looped; {dropped} repeated sentences were removed.]")


def patch_message(module):
    original = module.Message.to_chat_dict

    def to_chat_dict(self, **kwargs):
        message_dict = original(self, **kwargs)
        if message_dict.get("reasoning_content"):
            message_dict["reasoning_content"] = unloop(message_dict["reasoning_content"])
        return message_dict

    module.Message.to_chat_dict = to_chat_dict


def patch_condenser(module):
    import nexus_ledger
    nexus_ledger.install(module)


def patch_terminal_executor(module):
    import nexus_screen
    nexus_screen.patch_executor(module)


def patch_terminal_observation(module):
    import nexus_screen
    nexus_screen.patch_observation(module)


def patch_goal_judge(module):
    import nexus_goal
    nexus_goal.patch_judge(module)


def patch_goal_controller(module):
    import nexus_goal
    nexus_goal.patch_controller(module)


def patch_goal_resume(module):
    import nexus_goal
    nexus_goal.patch_event_service(module)


def patch_goal_route(module):
    import nexus_goal
    nexus_goal.patch_goal_route(module)


PATCHES = {
    "openhands.sdk.hooks.executor": (patch_hook_executor, "guard failure blocks execution"),
    "openhands.sdk.llm.llm": (patch_llm, "send_reasoning_content override"),
    "openhands.sdk.conversation.impl.local_conversation": (patch_conversation, "guard hook, switch_llm stats fix"),
    "openhands.sdk.agent.agent": (patch_agent, "a new message during an answer starts the step again"),
    "openhands.sdk.llm.message": (patch_message, "looped reasoning cleanup"),
    "openhands.sdk.context.condenser.llm_summarizing_condenser": (patch_condenser, "step ledger condenser"),
    "openhands.tools.terminal.impl": (patch_terminal_executor, "desktop images from @@attach"),
    "openhands.tools.terminal.definition": (patch_terminal_observation, "desktop images to the model"),
    "openhands.sdk.conversation.goal.judge": (patch_goal_judge, "goal judge for this PC, bounded transcript"),
    "openhands.sdk.conversation.goal.controller": (patch_goal_controller, "goal stops when the owner must answer"),
    "openhands.agent_server.event_service": (patch_goal_resume, "Russian goal resume message"),
    "openhands.agent_server.conversation_router": (patch_goal_route, "a repeated goal send starts nothing"),
}


class AfterImport:
    """Patches each SDK module right after it loads, before anything uses it."""

    def find_spec(self, name, path, target=None):
        if name not in PATCHES or getattr(self, "busy", False):
            return None
        self.busy = True
        try:
            spec = PathFinder.find_spec(name, path)
        finally:
            self.busy = False
        if spec is None or spec.loader is None:
            return spec
        patch, what = PATCHES.pop(name)
        if not PATCHES:
            sys.meta_path.remove(self)
        load = spec.loader.exec_module

        def exec_module(module):
            load(module)
            try:
                patch(module)
            except Exception as error:
                # Optional model/UI fixes may degrade; mandatory safety patches may not.
                if name in {"openhands.sdk.hooks.executor", "openhands.sdk.conversation.impl.local_conversation"}:
                    raise RuntimeError(f"Nexus mandatory SDK patch failed: {what}") from error
                print(f"[sdk-patch] {what} not applied: {error!r}", file=sys.stderr)

        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, AfterImport())
