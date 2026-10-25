"""agent-server loads this through PYTHONPATH (launcher/run.sh agent): one SDK fix until a release has it.

agent-server 1.58 (still in main) sends a model its earlier reasoning back only for a fixed list
of cloud models and ignores capability_overrides for it, so the local models saw each earlier
step with an empty <think> block although their templates expect the text there (the Tess card:
keep preserve_thinking on in agent loops). This honours capability_overrides
["send_reasoning_content"] from agent/config/profiles.json. Upstream: PR
OpenHands/software-agent-sdk#4446 adds exactly this override; drop this file once a release has it.
"""
import dataclasses
import os
import sys
from importlib.machinery import PathFinder

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = "openhands.sdk.llm.llm"

# Programs the agent runs inherit this environment: keep their Python free of this file.
_rest = [part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep)
         if part and os.path.abspath(part) != HERE]
if _rest:
    os.environ["PYTHONPATH"] = os.pathsep.join(_rest)
else:
    os.environ.pop("PYTHONPATH", None)


def patch(module):
    original = module.LLM._model_features

    def _model_features(self):
        features = original(self)
        wanted = (self.capability_overrides or {}).get("send_reasoning_content")
        if isinstance(wanted, bool) and wanted != features.send_reasoning_content:
            features = dataclasses.replace(features, send_reasoning_content=wanted)
        return features

    module.LLM._model_features = _model_features


class AfterImport:
    """Patches the SDK module right after it loads, before anything uses it."""

    def find_spec(self, name, path, target=None):
        if name != TARGET:
            return None
        sys.meta_path.remove(self)
        spec = PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        load = spec.loader.exec_module

        def exec_module(module):
            load(module)
            try:
                patch(module)
            except Exception as error:  # a changed SDK must still start, only without the fix
                print(f"[sdk-patch] send_reasoning_content override not applied: {error!r}", file=sys.stderr)

        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, AfterImport())
