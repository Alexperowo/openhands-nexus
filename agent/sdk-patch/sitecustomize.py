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
"""
import dataclasses
import os
import sys
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


def patch_conversation(module):
    from openhands.sdk.llm.llm_registry import RegistryEvent
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


PATCHES = {
    "openhands.sdk.llm.llm": (patch_llm, "send_reasoning_content override"),
    "openhands.sdk.conversation.impl.local_conversation": (patch_conversation, "switch_llm stats fix"),
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
            except Exception as error:  # a changed SDK must still start, only without the fix
                print(f"[sdk-patch] {what} not applied: {error!r}", file=sys.stderr)

        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, AfterImport())
