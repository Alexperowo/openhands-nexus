#!/usr/bin/env python3
"""
Tests/hardware/run_tinfield_long_context_sweep.py
Comprehensive Long-Context Benchmark for Tinfield 177B on llama-mainline b11276.
Systematically benchmarks:
- Context sizes: 32K, 50K, 70K, 90K, 110K, 131K
- Configurations:
  1. Candidate 1 (Production Winner): blk.44-45 CPU, ub=384, tb=3
  2. Candidate 2 (Headroom Winner):   blk.44-46 CPU, ub=512, tb=3
Measures: PP (tok/s), TTFT (s), TG (tok/s), Peak/Free VRAM GPU0/1, Peak RAM.
"""

import sys
import time
import subprocess
import re
import psutil
import json

LLAMA_CLI = r"K:\Project\llama-mainline\b11276\llama-cli.exe"
MODEL_PATH = r"D:\AI\Models\Tinfield-1-Mini\tinfield-1-mini-00001-of-00006.gguf"
VRAM_MANAGER = r"K:\Project\Config\vram_manager.py"

ENGINEERING_PARAGRAPH = (
    "In deep learning kernel optimization on heterogeneous GPU architectures, "
    "evaluating mixture-of-experts routing matrices involves sparse gate projection, "
    "top-k dispatch, and coalesced tensor memory access. Offloading MoE feed-forward "
    "expert weights to host DDR4 RAM across a PCIe 4.0 x4 bus introduces latency overheads "
    "that are mitigated by tuning micro-batch sizing (ubatch) and thread batching. "
)
# ~50 words ~ 65 tokens per paragraph. We scale this to generate target prompt lengths.

def clean_vram():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Stop-Process -Name llama-cli, llama-server -Force -ErrorAction SilentlyContinue"],
        timeout=10
    )
    subprocess.run([sys.executable, VRAM_MANAGER, "--wait-free", "1200", "--timeout", "10"], timeout=15)
    time.sleep(2)

def get_vram_snapshot():
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.free,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        lines = res.stdout.strip().splitlines()
        vram_info = {}
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 4:
                idx = int(parts[0])
                vram_info[f"gpu{idx}_used_mb"] = int(parts[1])
                vram_info[f"gpu{idx}_free_mb"] = int(parts[2])
                vram_info[f"gpu{idx}_total_mb"] = int(parts[3])
        return vram_info
    except Exception:
        return {}

def run_single_benchmark(name: str, ctx_size: int, prompt_tokens: int, ot_pattern: str, ub: int, tb: int):
    clean_vram()
    print(f"\n" + "=" * 75, flush=True)
    print(f"[*] RUNNING: {name} | Ctx: {ctx_size} | Prompt Target: ~{prompt_tokens} tokens", flush=True)
    print(f"    OT: {ot_pattern} | UB: {ub} | TB: {tb}", flush=True)
    print("=" * 75, flush=True)

    # Repeat paragraph to reach prompt_tokens (~65 tokens per repeat)
    repeats = max(1, prompt_tokens // 65)
    prompt_text = ENGINEERING_PARAGRAPH * repeats

    # Write prompt to temp file to avoid Windows 32KB command line limit (WinError 206)
    prompt_file = r"K:\Project\Tests\hardware\current_prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as pf:
        pf.write(prompt_text)

    cmd = [
        LLAMA_CLI,
        "-m", MODEL_PATH,
        "-c", str(ctx_size),
        "-ngl", "999",
        "-dev", "CUDA0,CUDA1",
        "-ts", "12.2,19.4",
        "-ot", ot_pattern,
        "-ctk", "q8_0",
        "-ctv", "q4_0",
        "-fa", "on",
        "-t", "6",
        "-b", "2048",
        "-ub", str(ub),
        "-tb", str(tb),
        "-n", "5",
        "-f", prompt_file,
        "-st"
    ]

    t_start = time.time()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    peak_ram = 0
    peak_vram_0 = 0
    peak_vram_1 = 0
    min_free_0 = 999999
    min_free_1 = 999999

    try:
        p_obj = psutil.Process(proc.pid)
    except Exception:
        p_obj = None

    # Polling loop
    while proc.poll() is None:
        if time.time() - t_start > 300: # 5 min timeout
            print("[!] Timeout 300s exceeded, terminating proc...", flush=True)
            subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {proc.pid} -Force"])
            break
        try:
            if p_obj and p_obj.is_running():
                rss = p_obj.memory_info().rss
                if rss > peak_ram:
                    peak_ram = rss
        except Exception:
            pass

        # Sample VRAM
        v_snap = get_vram_snapshot()
        if v_snap:
            u0 = v_snap.get("gpu0_used_mb", 0)
            u1 = v_snap.get("gpu1_used_mb", 0)
            f0 = v_snap.get("gpu0_free_mb", 0)
            f1 = v_snap.get("gpu1_free_mb", 0)
            if u0 > peak_vram_0: peak_vram_0 = u0
            if u1 > peak_vram_1: peak_vram_1 = u1
            if f0 < min_free_0 and f0 > 0: min_free_0 = f0
            if f1 < min_free_1 and f1 > 0: min_free_1 = f1

        time.sleep(0.3)

    stdout, _ = proc.communicate()
    elapsed = time.time() - t_start

    speed_match = re.search(r"\[\s*Prompt:\s*([\d\.]+)\s*t/s\s*\|\s*Generation:\s*([\d\.]+)\s*t/s\s*\]", stdout)
    prompt_tps = float(speed_match.group(1)) if speed_match else None
    gen_tps = float(speed_match.group(2)) if speed_match else None

    # Estimate TTFT
    # TTFT is roughly prompt_tokens / prompt_tps if prompt_tps is known
    ttft_s = (prompt_tokens / prompt_tps) if (prompt_tps and prompt_tps > 0) else None

    peak_ram_gb = peak_ram / (1024 ** 3)
    success = proc.returncode == 0 and prompt_tps is not None

    print(f"[+] Result for {name} ({ctx_size//1024}K):", flush=True)
    print(f"    Exit code:       {proc.returncode}", flush=True)
    print(f"    Prompt Eval:     {prompt_tps} tok/s", flush=True)
    print(f"    Est TTFT:        {ttft_s:.2f}s" if ttft_s else "    Est TTFT:        N/A", flush=True)
    print(f"    Generation:      {gen_tps} tok/s", flush=True)
    print(f"    Peak VRAM GPU0:  {peak_vram_0} MiB (Free: {min_free_0} MiB)", flush=True)
    print(f"    Peak VRAM GPU1:  {peak_vram_1} MiB (Free: {min_free_1} MiB)", flush=True)
    print(f"    Peak System RAM: {peak_ram_gb:.2f} GB", flush=True)

    return {
        "name": name,
        "ctx_size": ctx_size,
        "prompt_tokens": prompt_tokens,
        "success": success,
        "pp_tps": prompt_tps,
        "ttft_s": ttft_s,
        "tg_tps": gen_tps,
        "vram0_peak": peak_vram_0,
        "vram1_peak": peak_vram_1,
        "vram0_free": min_free_0,
        "vram1_free": min_free_1,
        "ram_gb": peak_ram_gb,
        "elapsed_s": elapsed
    }

def main():
    benchmarks = [
        {"ctx": 32768,  "prompt": 4096},
        {"ctx": 50000,  "prompt": 8192},
        {"ctx": 70000,  "prompt": 12288},
        {"ctx": 90000,  "prompt": 16384},
        {"ctx": 110000, "prompt": 20480},
        {"ctx": 131072, "prompt": 24576}
    ]

    all_results = []

    print("\n" + "#" * 80)
    print("# STARTING COMPREHENSIVE TINFIELD 177B LONG-CONTEXT SWEEP")
    print("#" * 80)

    # 1. Candidate 1: Production Winner (blk.44-45 CPU, ub=384, tb=3)
    for b in benchmarks:
        res = run_single_benchmark(
            name="Candidate 1 (blk.44-45 CPU, ub384, tb3)",
            ctx_size=b["ctx"],
            prompt_tokens=b["prompt"],
            ot_pattern=r"blk\.4[4-5]\..*=CPU",
            ub=384,
            tb=3
        )
        all_results.append(res)

    # 2. Candidate 2: Headroom Winner (blk.44-46 CPU, ub=512, tb=3)
    # Benchmark key points (50K, 70K, 131K)
    for b in [benchmarks[1], benchmarks[2], benchmarks[5]]:
        res = run_single_benchmark(
            name="Candidate 2 (blk.44-46 CPU, ub512, tb3)",
            ctx_size=b["ctx"],
            prompt_tokens=b["prompt"],
            ot_pattern=r"blk\.4[4-6]\..*=CPU",
            ub=512,
            tb=3
        )
        all_results.append(res)

    clean_vram()

    # Save results to json
    with open(r"K:\Project\Tests\hardware\tinfield_sweep_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Print summary table
    print("\n" + "=" * 110)
    print(f"{'Configuration':<38} | {'Ctx':<6} | {'Prompt':<7} | {'PP (t/s)':<9} | {'TTFT':<7} | {'TG (t/s)':<8} | {'VRAM0 (MB)':<10} | {'VRAM1 (MB)':<10}")
    print("-" * 110)
    for r in all_results:
        cfg = r["name"]
        ctx_k = f"{r['ctx_size']//1024}K"
        p_tok = f"{r['prompt_tokens']}"
        pp = f"{r['pp_tps']:.1f}" if r['pp_tps'] else "FAIL"
        ttft = f"{r['ttft_s']:.1f}s" if r['ttft_s'] else "N/A"
        tg = f"{r['tg_tps']:.1f}" if r['tg_tps'] else "FAIL"
        v0 = f"{r['vram0_peak']} ({r['vram0_free']})"
        v1 = f"{r['vram1_peak']} ({r['vram1_free']})"
        print(f"{cfg:<38} | {ctx_k:<6} | {p_tok:<7} | {pp:<9} | {ttft:<7} | {tg:<8} | {v0:<10} | {v1:<10}")
    print("=" * 110)

if __name__ == "__main__":
    main()
