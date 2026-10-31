"""Nexus skills load in the real SDK the way launcher/run.sh hands them over:
agent/state/skills/<name> -> ../../skills/<name>, found through OH_PERSISTENCE_DIR.

Run with the agent-server Python (./check does it in the SDK layer).
"""
import os
import sys
import tempfile
from pathlib import Path

SKILLS = Path(__file__).resolve().parent


def main():
    names = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
    assert names, "no skills in agent/skills"
    with tempfile.TemporaryDirectory() as tmp:
        agent = Path(tmp) / "agent"
        agent.mkdir()
        (agent / "skills").symlink_to(SKILLS)
        state = agent / "state"
        (state / "skills").mkdir(parents=True)
        for name in names:  # the same links run.sh makes
            (state / "skills" / name).symlink_to(Path("../../skills") / name)
        os.environ["OH_PERSISTENCE_DIR"] = str(state)
        os.environ["HOME"] = tmp  # no ~/.agents/skills of this PC in the result
        from openhands.sdk.context import (
            load_user_skills,  # after the environment is set
        )
        loaded = {skill.name: skill for skill in load_user_skills()}
    for name in names:
        skill = loaded.get(name)
        assert skill is not None, f"{name}: not loaded"
        assert skill.description and len(skill.description) > 40, f"{name}: no description"
        # AgentSkills format: the prompt lists only name and description, the text is read when needed
        assert skill.is_agentskills_format, f"{name}: not in AgentSkills format"
    print(f"OK: {', '.join(names)}")


if __name__ == "__main__":
    sys.exit(main())
