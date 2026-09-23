#!/usr/bin/env python3
"""
Tests/hardware/benchmark_max_vram_context.py
Finding the exact maximum context window for 208E (34.66 GB) 100% in VRAM with -ts 15,19.
"""

import os
import sys
import time
import subprocess

MODEL_PATH = r"K:\Project\Models\Qwen-122b\Qwen3.5-122B-A10B-208E-35GB.gguf"
LLAMA_CLI = r"K:\Project\LLM-tests\Qwen122B-Expert-Cache\bin\llama-cli.exe"

def get_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.free,memory.total", "--format=csv,noheader,nounits"],
            text=True
        )
        gpus = []
        for line in out.strip().splitlines():
            idx, used, free, total = [int(x.strip()) for x in line.split(",")]
            gpus.append({"index": idx, "used_mb": used, "free_mb": free, "total_mb": total})
        return gpus
    except Exception as e:
        return []

def clean_vram():
    subprocess.run(["powershell", "-NoProfile", "-Command", "Stop-Process -Name llama-cli, llama-server -Force -ErrorAction SilentlyContinue"], timeout=10)
    time.sleep(2)
    return get_vram()

def test_context(ctx_size, tensor_split="15,19"):
    sys.stdout.flush()
    print(f"\n========================================================", flush=True)
    print(f"[*] TESTING CONTEXT: {ctx_size} tokens ({ctx_size // 1024}K) | Split: {tensor_split}", flush=True)
    print(f"========================================================", flush=True)
    
    clean_vram()
    gpus_before = get_vram()
    if gpus_before:
        print(f"  VRAM before: GPU0={gpus_before[0]['free_mb']}MB free, GPU1={gpus_before[1]['free_mb']}MB free", flush=True)

    cmd = [
        LLAMA_CLI,
        "-m", MODEL_PATH,
        "-c", str(ctx_size),
        "-ngl", "999",
        "-dev", "CUDA0,CUDA1",
        "-ts", tensor_split,
        "-ctk", "q4_0",
        "-ctv", "q4_0",
        "-ub", "256",
        "-fa", "on",
        "-t", "6",
        "-p", "Describe the role of an architect in 15 words.",
        "-n", "20"
    ]

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        stdout, stderr = proc.communicate(timeout=120)
        dt = time.time() - t0
        ret = proc.returncode

        combined = stdout + "\n" + stderr
        is_oom = "cudaMalloc failed" in combined or "out of memory" in combined or "failed to allocate" in combined
        prompt_tps = None
        gen_tps = None
        
        for line in combined.splitlines():
            if "prompt eval time" in line and "tokens per second" in line:
                try:
                    parts = line.split("(")
                    if len(parts) > 1:
                        prompt_tps = float(parts[-1].split("tokens per second")[0].strip())
                except:
                    pass
            elif "eval time =" in line and "tokens per second" in line:
                try:
                    parts = line.split("(")
                    if len(parts) > 1:
                        gen_tps = float(parts[-1].split("tokens per second")[0].strip())
                except:
                    pass
            elif "Prompt:" in line and "Generation:" in line:
                try:
                    p_str = line.split("Prompt:")[1].split("t/s")[0].strip()
                    g_str = line.split("Generation:")[1].split("t/s")[0].strip()
                    prompt_tps = float(p_str)
                    gen_tps = float(g_str)
                except:
                    pass

        if ret == 0 and not is_oom:
            print(f"  [RESULT: SUCCESS] Code: {ret} in {dt:.1f}s", flush=True)
            print(f"  Prompt speed:     {prompt_tps} tok/s", flush=True)
            print(f"  Generation speed: {gen_tps} tok/s", flush=True)
            return {
                "ctx": ctx_size,
                "status": "PASS",
                "load_and_run_s": round(dt, 1),
                "prompt_tps": prompt_tps,
                "gen_tps": gen_tps,
            }
        else:
            print(f"  [RESULT: FAILED/OOM] Code: {ret}", flush=True)
            for l in combined.splitlines():
                if "error" in l.lower() or "failed" in l.lower() or "abort" in l.lower():
                    print(f"    {l.strip()}", flush=True)
            return {
                "ctx": ctx_size,
                "status": "OOM/FAIL",
                "error": "cudaMalloc failed or crash"
            }

    except subprocess.TimeoutExpired:
        proc.kill()
        print("  [RESULT: TIMEOUT]", flush=True)
        return {"ctx": ctx_size, "status": "TIMEOUT"}
    except Exception as e:
        print(f"  [RESULT: EXCEPTION] {e}", flush=True)
        return {"ctx": ctx_size, "status": "ERROR", "msg": str(e)}

def main():
    test_sizes = [
        8192,   # 8K
        16384,  # 16K
        24576,  # 24K
        32768,  # 32K
        36864,  # 36K
        40960,  # 40K
    ]
    
    results = []
    for ctx in test_sizes:
        res = test_context(ctx, tensor_split="15,19")
        results.append(res)
        time.sleep(3)
        if res["status"] != "PASS":
            print(f"\n[*] Reached failure threshold at context {ctx}.", flush=True)
            break

    print("\n" + "="*70, flush=True)
    print("           EMPIRICAL VRAM CONTEXT BENCHMARK SUMMARY (100% VRAM)", flush=True)
    print("="*70, flush=True)
    print(f"{'Context':<12} | {'Status':<10} | {'Gen (tok/s)':<12} | {'Prompt (tok/s)':<15} | {'Total Time':<10}", flush=True)
    print("-" * 70, flush=True)
    for r in results:
        ctx_k = f"{r['ctx']} ({r['ctx']//1024}K)"
        status = r.get("status")
        gen = f"{r.get('gen_tps')} t/s" if r.get('gen_tps') else "N/A"
        prompt = f"{r.get('prompt_tps')} t/s" if r.get('prompt_tps') else "N/A"
        t_time = f"{r.get('load_and_run_s')}s" if r.get('load_and_run_s') else "N/A"
        print(f"{ctx_k:<12} | {status:<10} | {gen:<12} | {prompt:<15} | {t_time:<10}", flush=True)
    print("="*70, flush=True)

if __name__ == "__main__":
    main()
