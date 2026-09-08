import litellm
import json

resp = litellm.completion(
    model="openai/D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
    api_base="http://127.0.0.1:8080/v1",
    api_key="sk-no-key",
    messages=[{"role": "user", "content": "What is 2+2? Answer in one word."}],
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    max_tokens=64
)

print("LiteLLM prompt_tokens:", resp.usage.prompt_tokens)
print("LiteLLM completion_tokens:", resp.usage.completion_tokens)
print("LiteLLM reasoning_content:", resp.choices[0].message.get("reasoning_content", ""))
print("LiteLLM content:", resp.choices[0].message.content)