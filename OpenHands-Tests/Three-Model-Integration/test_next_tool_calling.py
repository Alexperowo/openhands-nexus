import urllib.request
import json
import time
import os

SWAP_URL = "http://127.0.0.1:8080/v1/chat/completions"

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get current temperature and weather conditions for a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, e.g. San Francisco, Tokyo"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"]
                    }
                },
                "required": ["location"]
            }
        }
    }
]

payload = {
    "model": "openai/next",
    "messages": [
        {"role": "user", "content": "What is the weather like in Tokyo right now?"}
    ],
    "tools": tools,
    "tool_choice": "auto",
    "temperature": 0.1,
    "max_tokens": 1024
}

print("Sending tool call request to Next...")
t0 = time.time()
req = urllib.request.Request(
    SWAP_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req, timeout=120) as r:
    res = json.loads(r.read().decode("utf-8"))

elapsed = time.time() - t0
print(f"Response in {elapsed:.2f}s:")
print(json.dumps(res, indent=2))

msg = res["choices"][0]["message"]
tool_calls = msg.get("tool_calls", [])
print(f"\nTool calls detected: {len(tool_calls)}")
for tc in tool_calls:
    print(f"Function: {tc['function']['name']}, Arguments: {tc['function']['arguments']}")

assert len(tool_calls) > 0, "No tool calls produced by Next!"
print("\nTOOL CALLING TEST PASSED!")
