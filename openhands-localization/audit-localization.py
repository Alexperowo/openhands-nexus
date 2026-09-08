# Audit script for OpenHands Local Russian Localization
import json
import re
import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
EN_PATH = Path(appdata) / "npm/node_modules/@openhands/agent-canvas/build/locales/en/openhands.json"
RU_PATH = Path(__file__).resolve().parent / "ru.json"

# Recognized intentional non-translatable technical items
EXPLICIT_TECHNICAL_KEYS = {
    "COMMAND_MENU$SHORTCUT",              # '⌘K' (Mac keyboard symbol)
    "COMMON$JUPYTER",                     # 'Jupyter' (Brand name)
    "COMMON$PLAN_MD",                     # 'Plan.md' (Specific filename)
    "CONVERSATION$BUDGET_USAGE_FORMAT",   # '${currentCost} / ${maxBudget} ({usagePercentage}% {used})' (Variable interpolation pattern)
    "CONVERSATION$OVERVIEW_DIFF_ADDITIONS", # '+{{count}}' (Numeric diff prefix)
    "CONVERSATION$OVERVIEW_DIFF_DELETIONS", # '-{{count}}' (Numeric diff prefix)
    "CONVERSATION$OVERVIEW_UNAVAILABLE",  # '—' (Dash symbol)
    "GIT$GITHUB_API",                     # 'GitHub API' (Brand API)
    "GIT$GITLAB_API",                     # 'GitLab API' (Brand API)
    "GITHUB$AUTH_SCOPE",                  # 'openid email profile' (OAuth scopes)
    "LAUNCH$PLUGIN_PATH",                 # 'path:' (YAML syntax)
    "LAUNCH$PLUGIN_REF",                  # 'ref:' (YAML syntax)
    "SCHEMA$LLM$TOP_K$LABEL",             # 'Top K' (Hyperparameter name)
    "SCHEMA$LLM$TOP_P$LABEL",             # 'Top P' (Hyperparameter name)
    "SETTINGS$AZURE_DEVOPS",              # 'Azure DevOps' (Brand name)
    "SETTINGS$MCP_DEFAULT_CONFIG",        # JSON config template
    "SETTINGS$MCP_HEADERS_PLACEHOLDER",   # HTTP header format
    "SETTINGS$MCP_OAUTH_CLIENT_ID_PLACEHOLDER",     # 'client-id' (Technical ID)
    "SETTINGS$MCP_OAUTH_CLIENT_SECRET_PLACEHOLDER", # 'client-secret' (Technical secret)
    "SETTINGS$PRO_PILL",                  # 'Pro' (Tier badge)
    "SETTINGS$SKILLS_PILLS_MORE",         # '+{{count}}' (Badge counter)
    "SETTINGS$SLACK",                     # 'Slack' (Brand name)
    "SETTINGS$TITLE_GENERATION_PROFILE_OPTION", # '{{name}} · {{model}}' (Format string)
    "SETTINGS$VERSION_NPM_RECOMMENDED",   # 'npm' (Package manager)
    "WORKSPACE$JUPYTER_TAB_LABEL"         # 'Jupyter' (Brand tab name)
}

def is_technical_string(k: str, text: str) -> bool:
    if k in EXPLICIT_TECHNICAL_KEYS:
        return True

    t = text.strip()
    if not t:
        return True
    
    # Placeholders / tags only
    if re.match(r"^(\{\{[^}]+\}\}|<[^>]+>|\s)+$", t):
        return True

    # Punctuation / symbols / keyboard shortcuts e.g. "⌘K", "Ctrl+K", ":"
    if re.match(r"^[\s\-_:;,.|/\\()\[\]{}'\"*+~`=<>0-9%#@!?&↑↓←→⏎⌘⌥⇧⌃]+$", t):
        return True
    
    # Pure URLs or paths or branch names
    if re.match(r"^https?://[^\s]+$", t) or re.match(r"^/[a-zA-Z0-9_\-./]+$", t):
        return True
    
    # Version tags like v{{version}}, main, master
    if t in {"main", "master", "HEAD", "latest"} or re.match(r"^v\{\{[^}]+\}\}$", t):
        return True

    # Pure env vars or code constants / examples
    if re.match(r"^[A-Z0-9_]+(=[a-zA-Z0-9_]+)?$", t) or t.startswith("tvly-"):
        return True
    
    # Single acronyms or known tech brand names
    known_tech = {
        "openhands", "all-hands", "github", "gitlab", "docker", "python", "node.js",
        "api", "mcp", "url", "id", "cli", "sdk", "llm", "ui", "os", "git", "ssh", "oauth",
        "http", "https", "json", "yaml", "toml", "bash", "linux", "macos", "windows",
        "vnc", "vscode", "vs code", "copilot", "posthog", "monaco", "android", "adb",
        "bearer", "bearer <token>", "email", "e-mail", "llm profile", "agent-server", "openhands cloud"
    }
    if t.lower() in known_tech:
        return True
    
    # Model IDs like anthropic/claude-3-5-sonnet-20241022
    if re.match(r"^[a-zA-Z0-9_\-]+/[a-zA-Z0-9._\-]+$", t):
        return True
        
    return False

def extract_placeholders(s: str) -> list[str]:
    return re.findall(r"\{\{[^}]+\}\}", s)

def extract_tags(s: str) -> list[str]:
    return re.findall(r"</?[a-zA-Z0-9_\-]+(?:\s+[^>]*)?>", s)

def main():
    if not EN_PATH.exists():
        print(f"Error: EN file not found: {EN_PATH}", file=sys.stderr)
        sys.exit(1)
    if not RU_PATH.exists():
        print(f"Error: RU file not found: {RU_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(EN_PATH, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(RU_PATH, "r", encoding="utf-8") as f:
        ru_data = json.load(f)

    en_keys = set(en_data.keys())
    ru_keys = set(ru_data.keys())

    missing_in_ru = sorted(list(en_keys - ru_keys))
    extra_in_ru = sorted(list(ru_keys - en_keys))
    common_keys = sorted(list(en_keys & ru_keys))

    exact_matches = []
    intentional_matches = []
    suspicious_matches = []

    for k in common_keys:
        en_val = en_data[k]
        ru_val = ru_data[k]
        if en_val == ru_val:
            exact_matches.append((k, en_val))
            if is_technical_string(k, en_val):
                intentional_matches.append((k, en_val))
            else:
                suspicious_matches.append((k, en_val))

    placeholder_mismatches = []
    for k in common_keys:
        en_ph = extract_placeholders(en_data[k])
        ru_ph = extract_placeholders(ru_data[k])
        if sorted(en_ph) != sorted(ru_ph):
            placeholder_mismatches.append({
                "key": k,
                "en_val": en_data[k],
                "ru_val": ru_data[k],
                "en_ph": en_ph,
                "ru_ph": ru_ph
            })

    tag_mismatches = []
    for k in common_keys:
        en_tags = extract_tags(en_data[k])
        ru_tags = extract_tags(ru_data[k])
        if sorted(en_tags) != sorted(ru_tags):
            tag_mismatches.append({
                "key": k,
                "en_val": en_data[k],
                "ru_val": ru_data[k],
                "en_tags": en_tags,
                "ru_tags": ru_tags
            })

    print("=" * 60)
    print("         OPENHANDS LOCAL - AUDIT REPORT")
    print("=" * 60)
    print(f"Total EN keys:            {len(en_keys)}")
    print(f"Total RU keys:            {len(ru_keys)}")
    print(f"Missing RU keys:          {len(missing_in_ru)}")
    print(f"Extra RU keys:            {len(extra_in_ru)}")
    print(f"Exact EN == RU matches:   {len(exact_matches)}")
    print(f"  - Intentional technical:{len(intentional_matches)}")
    print(f"  - Suspicious UI strings:{len(suspicious_matches)}")
    print(f"Placeholder mismatches:   {len(placeholder_mismatches)}")
    print(f"Tag mismatches:           {len(tag_mismatches)}")
    print("=" * 60)

    if suspicious_matches:
        print(f"\n--- SUSPICIOUS EN == RU MATCHES ({len(suspicious_matches)}) ---")
        for k, v in suspicious_matches:
            print(f"[{k}] => {v!r}")

    if placeholder_mismatches:
        print(f"\n--- PLACEHOLDER MISMATCHES ({len(placeholder_mismatches)}) ---")
        for pm in placeholder_mismatches:
            print(f"[{pm['key']}]")
            print(f"  EN: {pm['en_val']} (ph: {pm['en_ph']})")
            print(f"  RU: {pm['ru_val']} (ph: {pm['ru_ph']})")

    if tag_mismatches:
        print(f"\n--- TAG MISMATCHES ({len(tag_mismatches)}) ---")
        for tm in tag_mismatches:
            print(f"[{tm['key']}]")
            print(f"  EN: {tm['en_val']} (tags: {tm['en_tags']})")
            print(f"  RU: {tm['ru_val']} (tags: {tm['ru_tags']})")

    report = {
        "total_en_keys": len(en_keys),
        "total_ru_keys": len(ru_keys),
        "missing_in_ru": missing_in_ru,
        "extra_in_ru": extra_in_ru,
        "exact_matches_count": len(exact_matches),
        "intentional_matches_count": len(intentional_matches),
        "suspicious_matches_count": len(suspicious_matches),
        "placeholder_mismatches_count": len(placeholder_mismatches),
        "tag_mismatches_count": len(tag_mismatches),
        "intentional_matches": [{"key": k, "value": v} for k, v in intentional_matches],
        "suspicious_matches": [{"key": k, "value": v} for k, v in suspicious_matches],
        "placeholder_mismatches": placeholder_mismatches,
        "tag_mismatches": tag_mismatches
    }

    out_file = Path(r"K:\Project\OpenHands-Tests\Russian-Localization\locale-audit.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed JSON report written to: {out_file}")

if __name__ == "__main__":
    main()
