import os
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def check_all():
    print("=" * 70)
    print("PRE-FLIGHT AUDIT: AGENT PROFILES & TOOLS")
    print("=" * 70)

    # 1. Agent profiles
    agent_dir = os.path.expanduser("~/.openhands/agent-profiles")
    if not os.path.exists(agent_dir):
        print(f"[!] {agent_dir} does not exist!")
        return

    profiles = [f for f in os.listdir(agent_dir) if f.endswith(".json")]
    print(f"Found {len(profiles)} agent profile(s) in {agent_dir}:")
    for f in sorted(profiles):
        p_path = os.path.join(agent_dir, f)
        with open(p_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        name = data.get("name", f)
        agent_type = data.get("agent_type", data.get("agent", "CodeActAgent"))
        tools = data.get("tools", [])
        llm_profile = data.get("llm_profile", data.get("llm_config", {}))
        mcp = data.get("mcp_server_refs", data.get("mcp_servers", []))
        llm_ref = data.get("llm_profile_ref", "")
        enable_switch = data.get("enable_switch_llm_tool", False)
        print(f"\n- Profile: [{name}] (file: {f})")
        print(f"  ID: {data.get('id')}")
        print(f"  Agent Type: {agent_type}")
        print(f"  Tools: {'All Standard (CodeAct default)' if tools is None else tools}")
        print(f"  Enable switch_llm_tool: {enable_switch}")
        print(f"  MCP Servers: {mcp}")
        print(f"  LLM Profile ref: {llm_ref}")

    # 2. LLM Profiles
    print("\n" + "=" * 70)
    print("PRE-FLIGHT AUDIT: LLM PROFILES (Provider Connections / Models)")
    print("=" * 70)
    llm_dir = os.path.expanduser("~/.openhands/profiles")
    if os.path.exists(llm_dir):
        llm_files = [f for f in os.listdir(llm_dir) if f.endswith(".json")]
        print(f"Found {len(llm_files)} LLM profiles in {llm_dir}:")
        for f in sorted(llm_files):
            with open(os.path.join(llm_dir, f), "r", encoding="utf-8") as fp:
                ldata = json.load(fp)
            pname = ldata.get("name", f)
            model = ldata.get("model", "")
            base_url = ldata.get("base_url", "")
            max_out = ldata.get("max_output_tokens", "")
            temp = ldata.get("temperature", "")
            extra = ldata.get("litellm_extra_body", {})
            thinking = extra.get("chat_template_kwargs", {}).get("enable_thinking", "unset")
            print(f"  - [{pname}] model='{model}', max_out={max_out}, enable_thinking={thinking}")

    # 3. Working Profile Templates & State
    print("\n" + "=" * 70)
    print("PRE-FLIGHT AUDIT: WORKING PROFILES & REASONING MODES")
    print("=" * 70)
    wp_dir = os.path.expanduser("~/.openhands/working-profiles")
    if os.path.exists(wp_dir):
        wp_files = [f for f in os.listdir(wp_dir) if f.endswith(".json")]
        print(f"Found {len(wp_files)} working profiles:")
        for f in sorted(wp_files):
            with open(os.path.join(wp_dir, f), "r", encoding="utf-8") as fp:
                wp = json.load(fp)
            w_id = wp.get("id", f)
            w_name = wp.get("name", "")
            w_kind = wp.get("kind", "")
            reasoning = wp.get("reasoning", {})
            modes = reasoning.get("modes", [])
            mode_names = [f"{m.get('id')} ({m.get('label')}: {m.get('target_llm_profile_name')})" for m in modes]
            print(f"\n  [{w_name}] id='{w_id}', kind='{w_kind}'")
            print(f"    Supported: {reasoning.get('supported')}, Default: {reasoning.get('default_mode_id')}")
            print(f"    Modes ({len(modes)}): {', '.join(mode_names)}")

    state_file = os.path.expanduser("~/.openhands/working-profile-state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as fp:
            st = json.load(fp)
        print(f"\nCurrent Working Profile State:\n{json.dumps(st, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    check_all()
