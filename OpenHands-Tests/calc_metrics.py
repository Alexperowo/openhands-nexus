import json

with open(r"K:\Project\OpenHands-Tests\Android-Smoke-01\tool-calls.json", "r", encoding="utf-8") as f:
    tool_calls = json.load(f)

# Count tools by name
tool_counts = {}
for tc in tool_calls:
    name = tc.get("tool_name") or "unknown"
    tool_counts[name] = tool_counts.get(name, 0) + 1

print("Tool call counts:")
for k, v in sorted(tool_counts.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

mcp_tool_calls = sum(v for k, v in tool_counts.items() if k.startswith("android_"))
print(f"\nTotal MCP Tool Calls: {mcp_tool_calls}")
print(f"Total Action Events / Tool Calls: {len(tool_calls)}")