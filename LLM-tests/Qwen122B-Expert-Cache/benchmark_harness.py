import json
import time
import urllib.request
import subprocess
import os
import psutil

TASKS = [
    {
        "id": "task1_coding",
        "name": "Async Token Bucket Rate Limiter",
        "prompt": "Write a production-ready asynchronous Python token bucket rate limiter class with thread safety, burst capacity, millisecond refill resolution, and context manager support. Include unit tests."
    },
    {
        "id": "task2_architecture",
        "name": "High-Throughput Low-Latency Market Data Pipeline",
        "prompt": "Design an ultra-low latency event-driven market data pipeline processing 500,000 events/sec. Explain memory layout, zero-copy deserialization, lock-free ring buffers, and cache affinity."
    },
    {
        "id": "task3_reasoning",
        "name": "Raft Consensus Partition & Election Analysis",
        "prompt": "A distributed key-value store uses Raft consensus across 5 nodes. Node 1 is leader (term 3). Nodes 2 and 3 receive appendEntries up to index 150. Node 4 and 5 are partitioned at index 140. Node 1 crashes. Analyze step by step what happens during leader election, which nodes can become leader, and what happens to uncommitted log entries."
    }
]

def get_gpu_memory():
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.free,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        lines = [line.strip().split(", ") for line in res.stdout.strip().splitlines() if line.strip()]
        return {
            f"gpu_{l[0]}": {
                "used_mib": float(l[1]),
                "free_mib": float(l[2]),
                "total_mib": float(l[3])
            } for l in lines
        }
    except Exception as e:
        return {"error": str(e)}

def get_system_ram():
    mem = psutil.virtual_memory()
    return {
        "used_gib": round(mem.used / (1024**3), 2),
        "total_gib": round(mem.total / (1024**3), 2),
        "percent": mem.percent
    }

def run_single_prompt(endpoint_url, model_name, prompt, max_tokens=512, temp=0.6, top_p=0.95, seed=42):
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are an expert systems software engineer and computer science architect."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temp,
        "top_p": top_p,
        "seed": seed,
        "stream": True
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint_url}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    start_time = time.perf_counter()
    first_token_time = None
    chunks = []
    reasoning_content = []
    content = []
    
    with urllib.request.urlopen(req) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                chunk_str = line[6:]
                try:
                    chunk = json.loads(chunk_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if first_token_time is None and (delta.get("content") or delta.get("reasoning_content")):
                        first_token_time = time.perf_counter()
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        reasoning_content.append(delta["reasoning_content"])
                    if "content" in delta and delta["content"]:
                        content.append(delta["content"])
                except Exception:
                    pass
                    
    end_time = time.perf_counter()
    total_wall_sec = end_time - start_time
    ttft_sec = (first_token_time - start_time) if first_token_time else total_wall_sec
    gen_time_sec = total_wall_sec - ttft_sec
    
    full_reasoning = "".join(reasoning_content)
    full_text = "".join(content)
    
    # Estimate token count (or from usage if available, approx 3.8 chars/tok for Russian/English code)
    # If llama.cpp emitted finish chunk with usage, we can extract or approximate
    comp_chars = len(full_reasoning) + len(full_text)
    # Estimate tokens conservatively: approx 3.7 chars per token for technical English/Russian
    approx_tokens = max(1, int(comp_chars / 3.7))
    
    decode_tps = (approx_tokens / gen_time_sec) if gen_time_sec > 0 else 0.0
    
    return {
        "ttft_sec": round(ttft_sec, 3),
        "total_wall_sec": round(total_wall_sec, 3),
        "gen_time_sec": round(gen_time_sec, 3),
        "approx_tokens": approx_tokens,
        "decode_tps": round(decode_tps, 2),
        "reasoning_len": len(full_reasoning),
        "content_len": len(full_text),
        "output_snippet": (full_text[:200] if full_text else full_reasoning[:200])
    }

def run_benchmark_suite(experiment_id, endpoint_url, model_name, output_dir, runs_per_task=2):
    print(f"=== Starting Benchmark Suite: {experiment_id} ===")
    print(f"Endpoint: {endpoint_url}, Model: {model_name}")
    
    gpu_before = get_gpu_memory()
    ram_before = get_system_ram()
    print(f"Baseline RAM: {ram_before['used_gib']} GB / {ram_before['total_gib']} GB")
    print(f"Baseline GPU: {gpu_before}")
    
    suite_results = {
        "experiment_id": experiment_id,
        "endpoint_url": endpoint_url,
        "model_name": model_name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware_before": {
            "gpu": gpu_before,
            "ram": ram_before
        },
        "tasks": {}
    }
    
    for task in TASKS:
        task_id = task["id"]
        print(f"\n--- Running {task['name']} ({runs_per_task} runs) ---")
        task_runs = []
        for run_idx in range(runs_per_task):
            print(f"  Run {run_idx+1}/{runs_per_task}...", end="", flush=True)
            run_metrics = run_single_prompt(
                endpoint_url=endpoint_url,
                model_name=model_name,
                prompt=task["prompt"]
            )
            print(f" TTFT: {run_metrics['ttft_sec']}s | Gen: {run_metrics['gen_time_sec']}s | Est Tok: {run_metrics['approx_tokens']} | TPS: {run_metrics['decode_tps']}")
            task_runs.append(run_metrics)
            time.sleep(1)
            
        tps_list = [r["decode_tps"] for r in task_runs]
        ttft_list = [r["ttft_sec"] for r in task_runs]
        suite_results["tasks"][task_id] = {
            "name": task["name"],
            "runs": task_runs,
            "summary": {
                "tps_mean": round(sum(tps_list)/len(tps_list), 2),
                "tps_min": min(tps_list),
                "tps_max": max(tps_list),
                "ttft_mean": round(sum(ttft_list)/len(ttft_list), 2)
            }
        }
        
    gpu_after = get_gpu_memory()
    ram_after = get_system_ram()
    suite_results["hardware_after"] = {
        "gpu": gpu_after,
        "ram": ram_after
    }
    
    out_file = os.path.join(output_dir, f"{experiment_id}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(suite_results, f, indent=2, ensure_ascii=False)
    print(f"\n[PASSED] Results saved to {out_file}")
    return suite_results

if __name__ == "__main__":
    import sys
    exp_id = sys.argv[1] if len(sys.argv) > 1 else "QWEN122-PROD-BASELINE"
    endpoint = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8080"
    model = sys.argv[3] if len(sys.argv) > 3 else "qwen122"
    out_dir = r"K:\Project\LLM-tests\Qwen122B-Expert-Cache\results"
    run_benchmark_suite(exp_id, endpoint, model, out_dir, runs_per_task=2)
