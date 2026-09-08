import jinja2
import urllib.request
import json

r = urllib.request.urlopen('http://127.0.0.1:8080/props')
props = json.loads(r.read().decode())
tmpl_str = props['chat_template']

env = jinja2.Environment(loader=jinja2.BaseLoader())
tmpl = env.from_string(tmpl_str)

messages = [{"role": "user", "content": "Hello"}]

for mode, kwargs in [
    ("Default", {}),
    ("enable_thinking=False", {"enable_thinking": False}),
    ("enable_thinking=True, reasoning_effort=low", {"enable_thinking": True, "reasoning_effort": "low"}),
    ("enable_thinking=True, reasoning_effort=medium", {"enable_thinking": True, "reasoning_effort": "medium"}),
    ("enable_thinking=True, reasoning_effort=xhigh", {"enable_thinking": True, "reasoning_effort": "xhigh"}),
]:
    res = tmpl.render(messages=messages, add_generation_prompt=True, **kwargs)
    print(f"=== {mode} ===")
    print("PROMPT OUTPUT:\n" + repr(res))
    print()