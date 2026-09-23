import sys
import time
import requests
import json

URL = "http://127.0.0.1:8080/v1/chat/completions"

prompt = (
    "Напиши исчерпывающее, глубокое и детальное техническое руководство по внутреннему устройству "
    "и оптимизации MoE (Mixture of Experts) архитектур в современных LLM (таких как Qwen, DeepSeek, Mixtral). "
    "Опиши подробно: 1) математику Top-K роутинга и балансировку экспертов (auxiliary loss, expert capacity); "
    "2) проблемы Memory Wall, пропускной способности памяти VRAM vs DRAM при оффлоаде; "
    "3) fused MoE ядра в CUDA (Cutlass, Triton) и упаковку весов; "
    "4) CUDA Graphs и почему dynamic control flow в MoE ломает статический захват графов; "
    "5) Flash Attention v2/v3 и поведение KV-кэша при контексте до 128K токенов; "
    "6) методы прунинга экспертов (статический по L2-норме и динамический активационный аудит). "
    "Пиши максимально подробно, развернуто и глубоко с псевдокодом и формулами, без сокращений."
)

payload = {
    "model": "qwen122",
    "messages": [
        {"role": "user", "content": prompt}
    ],
    "temperature": 0.6,
    "top_p": 0.95,
    "max_tokens": 4096,
    "stream": True
}

print(f"Connecting to {URL} with model qwen122...")
t0 = time.time()
ttft = None
first_chunk = True
token_count = 0
last_report_tokens = 0
last_report_time = t0

try:
    with requests.post(URL, json=payload, stream=True, timeout=1800) as resp:
        if resp.status_code != 200:
            print(f"Error HTTP {resp.status_code}: {resp.text}")
            sys.exit(1)
            
        print("Connected! Receiving stream...")
        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode('utf-8', errors='ignore')
            if line_str.startswith("data: "):
                data_str = line_str[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content") or delta.get("reasoning_content") or ""
                    if content:
                        now = time.time()
                        if ttft is None:
                            ttft = now - t0
                            print(f"TTFT: {ttft:.2f}s")
                            last_report_time = now
                        token_count += 1
                        
                        # Report every 200 tokens
                        if token_count - last_report_tokens >= 200:
                            elapsed_interval = now - last_report_time
                            interval_speed = (token_count - last_report_tokens) / elapsed_interval if elapsed_interval > 0 else 0
                            cumulative_speed = token_count / (now - (t0 + ttft)) if (now - (t0 + ttft)) > 0 else 0
                            print(f"Token {token_count:5d} | Interval speed: {interval_speed:5.2f} tok/s | Cumulative speed: {cumulative_speed:5.2f} tok/s")
                            last_report_tokens = token_count
                            last_report_time = now
                except Exception as e:
                    pass

    t_end = time.time()
    gen_time = t_end - (t0 + (ttft or 0))
    total_speed = token_count / gen_time if gen_time > 0 else 0
    print(f"\nFinished: {token_count} tokens generated in {gen_time:.2f}s ({total_speed:.2f} tok/s).")
except Exception as e:
    print(f"Exception during stream: {e}")
