"""Prepare approved UI sources in /tmp. Never extracts secrets, dist or *.bak*."""
import pathlib
import re
import sys
import tarfile
import tempfile

project = pathlib.Path(__file__).resolve().parent.parent
directory = pathlib.Path(tempfile.mkdtemp(prefix="ohn-ui-baseline-"))
with tarfile.open(sys.argv[1]) as archive:
    for member in archive.getmembers():
        name = member.name
        if not member.isfile() or ".bak" in name or ".." in pathlib.PurePosixPath(name).parts:
            continue
        if not (name.startswith("src/") or name in ("package.json", "vite.config.ts", "index.html")):
            continue
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(member).read())
config_path = directory / "vite.config.ts"
config = re.sub(r"const sessionEnv = [\s\S]*?export default defineConfig", 'const sessionApiKey = "";\n\nexport default defineConfig', config_path.read_text())
config = config.replace("plugins: [", "envDir: false,\n    plugins: [")
config_path.write_text(config)
(directory / "node_modules").symlink_to(project / "node_modules", target_is_directory=True)
(directory / "dev").mkdir()
for name in ("build.mjs", "index.html", "replay.tsx"):
    (directory / "dev" / name).write_bytes((project / "dev" / name).read_bytes())
pathlib.Path("/tmp/ohn-ui-baseline-source.txt").write_text(str(directory))
print(directory)
