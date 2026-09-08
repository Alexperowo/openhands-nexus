import os, shutil, datetime, difflib

cfg_path = r"K:\Project\llama-swap\config.yaml"
backup_dir = r"K:\Project\Archive\backups"
evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_evidence"

os.makedirs(backup_dir, exist_ok=True)
os.makedirs(evidence_dir, exist_ok=True)

# 1. Backup with timestamp
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_file = os.path.join(backup_dir, f"config.yaml.backup.{timestamp}")
shutil.copy2(cfg_path, backup_file)
print("Backup created at:", backup_file)

# 2. Read original content
with open(cfg_path, "r", encoding="utf-8") as f:
    orig_lines = f.readlines()

# 3. Replace D:\Project\models\ with K:\Project\Models\Qwen3.8\
new_lines = []
for line in orig_lines:
    new_line = line.replace(
        r"D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        r"K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
    )
    new_lines.append(new_line)

# 4. Write new config
with open(cfg_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

# 5. Compute diff
diff = list(difflib.unified_diff(
    orig_lines,
    new_lines,
    fromfile="llama-swap/config.yaml (original)",
    tofile="llama-swap/config.yaml (switched to K:)",
    lineterm=""
))

diff_text = "\n".join(diff)
print("--- EXACT DIFF ---")
print(diff_text)

# 6. Save diff to evidence
diff_path = os.path.join(evidence_dir, "qwen_config_diff.txt")
with open(diff_path, "w", encoding="utf-8") as f:
    f.write(diff_text)
print("Diff saved to:", diff_path)
