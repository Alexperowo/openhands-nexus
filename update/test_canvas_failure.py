"""Real npm/build failure and recovery, exclusively in an existing /tmp copy."""
import argparse
import json
from pathlib import Path

from nexus_update import Updater, UpdateError, digest, parse_args


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sandbox")
    args = parser.parse_args()
    updater = Updater(parse_args(["canvas", "1.33.0", "--sandbox", args.sandbox]))
    updater.state.mkdir(exist_ok=True)
    original_version = updater.installed_canvas()
    assert original_version == "1.30.1", "This regression test expects a 1.30.1 sandbox"
    paths = [updater.root / project / name for project in ("agent", "ui")
             for name in ("package.json", "package-lock.json")]
    before = {str(path): digest(path) for path in paths}
    source = updater.root / "ui/src/main.tsx"
    original = source.read_text()
    run = updater.run
    injected = False

    def fail_once(command, **kwargs):
        nonlocal injected
        assert str(command[0]) != "systemctl", "No unit calls are allowed in this test"
        if command == ["npm", "run", "build"] and not injected:
            injected = True
            source.write_text(original + '\nimport "../node_modules/@openhands/agent-canvas/dist/nexus-update-absent.js";\n')
            try:
                return run(command, **kwargs)
            finally:
                source.write_text(original)
        return run(command, **kwargs)

    updater.run = fail_once
    try:
        updater.canvas()
    except UpdateError:
        assert injected
    else:
        raise AssertionError("Broken deep import unexpectedly built")
    assert updater.installed_canvas() == original_version
    assert source.read_text() == original
    assert all(digest(path) == before[str(path)] for path in paths)
    assert (updater.root / "ui/dist/index.html").is_file()
    result = {"expected_build_failure": True, "restored_version": original_version,
              "manifest_sha256_restored": True, "source_restored": True, "units_restarted": False}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
