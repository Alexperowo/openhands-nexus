#!/usr/bin/env python3
"""
Tests/hardware/run_real_70k_prompt_benchmark.py
Direct empirical benchmark of REAL 32K, 50K, 60K, 70K input prompt tokens
strictly inside a fixed context window of 131,072 (131K).

Compares:
- Candidate 2 (Ingestion / Headroom Profile): blk.44-46 CPU, ub=512, tb=3
- Candidate 1 (Generation Profile):          blk.44-45 CPU, ub=384, tb=3

Measures:
- Total Prompt Ingestion Time (s)
- Actual PP tok/s
- Est TTFT (s)
- TG tok/s (for 5 tokens)
- Peak & Free VRAM on GPU 0 and GPU 1
- Peak System RAM
- Exact pass/fail/OOM status
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
PROMPT_FILE = r"K:\Project\Tests\hardware\real_prompt.txt"

# Real engineering text paragraph (~65 tokens)
ENGINEERING_PARAGRAPH = (
    "In deep learning kernel optimization on heterogeneous GPU architectures, "
    "evaluating mixture-of-experts routing matrices involves sparse gate projection, "
    "top-k dispatch, and coalesced tensor memory access. Offloading MoE feed-forward "
    "expert weights to host DDR4 RAM across a PCIe 4.0 x4 bus introduces latency overheads "
    "that are mitigated by tuning micro-batch sizing (ubatch) and thread batching. "
)

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

def run_real_prompt_test(name: str, target_prompt_tokens: int, ot_pattern: str, ub: int, tb: int):
    clean_vram()
    print(f"\n" + "=" * 80, flush=True)
    print(f"[*] RUNNING: {name} | REAL PROMPT: {target_prompt_tokens} tokens | CTX: 131072", flush=True)
    print(f"    OT: {ot_pattern} | UB: {ub} | TB: {tb}", flush=True)
    print("=" * 80, flush=True)

    # 1 paragraph ~ 65 tokens
    repeats = max(1, target_prompt_tokens // 65)
    prompt_text = ENGINEERING_PARAGRAPH * repeats

    with open(PROMPT_FILE, "w", encoding="utf-8") as pf:
        pf.write(prompt_text)

    cmd = [
        LLAMA_CLI,
        "-m", MODEL_PATH,
        "-c", "131072",
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
        "-f", PROMPT_FILE,
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

    # Polling loop (max timeout 600s = 10 min for huge 70K prompt)
    while proc.poll() is None:
        if time.time() - t_start > 600:
            print("[!] Timeout 600s exceeded, terminating proc...", flush=True)
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

        time.sleep(0.5)

    stdout, _ = proc.communicate()
    elapsed = time.time() - t_start

    speed_match = re.search(r"\[\s*Prompt:\s*([\d\.]+)\s*t/s\s*\|\s*Generation:\s*([\d\.]+)\s*t/s\s*\]", stdout)
    prompt_tps = float(speed_match.group(1)) if speed_match else None
    gen_tps = float(speed_match.group(2)) if speed_match else None

    # Exact TTFT from prompt_tps
    ttft_s = (target_prompt_tokens / prompt_tps) if (prompt_tps and prompt_tps > 0) else None
    peak_ram_gb = peak_ram / (1024 ** 3)
    success = proc.returncode == 0 and prompt_tps is not None

    status_str = "SUCCESS" if success else ("OOM" if "out of memory" in stdout.lower() else f"FAIL (code {proc.returncode})")

    print(f"[+] Result for {name} ({target_prompt_tokens//1000}K prompt):", flush=True)
    print(f"    Status:          {status_str}", flush=True)
    print(f"    Total Time:      {elapsed:.2f}s", flush=True)
    print(f"    Prompt Eval:     {prompt_tps} tok/s" if prompt_tps else "    Prompt Eval:     FAILED", flush=True)
    print(f"    Est TTFT:        {ttft_s:.2f}s" if ttft_s else "    Est TTFT:        N/A", flush=True)
    print(f"    Generation:      {gen_tps} tok/s" if gen_tps else "    Generation:      FAILED", flush=True)
    print(f"    Peak VRAM GPU0:  {peak_vram_0} MiB (Free: {min_free_0} MiB)", flush=True)
    print(f"    Peak VRAM GPU1:  {peak_vram_1} MiB (Free: {min_free_1} MiB)", flush=True)
    print(f"    Peak System RAM: {peak_ram_gb:.2f} GB", flush=True)

    return {
        "name": name,
        "prompt_tokens": target_prompt_tokens,
        "status": status_str,
        "success": success,
        "pp_tps": prompt_tps,
        "ttft_s": ttft_s,
        "tg_tps": gen_tps,
        "total_time_s": elapsed,
        "vram0_peak": peak_vram_0,
        "vram1_peak": peak_vram_1,
        "vram0_free": min_free_0,
        "vram1_free": min_free_1,
        "ram_gb": peak_ram_gb
    }

def main():
    prompt_targets = [32768, 50000, 60000, 70000]
    all_results = []

    print("\n" + "#" * 80)
    print("# BENCHMARKING REAL 32K, 50K, 60K, 70K INGESTION IN FIXED 131K CONTEXT")
    print("#" * 80)

    # First test Candidate 2 (Ingestion Champion: blk.44-46 CPU, ub512, tb3)
    for p_size in prompt_targets:
        res = run_real_prompt_test(
            name="Candidate 2 (blk.44-46 CPU, ub512, tb3)",
            target_prompt_tokens=p_size,
            ot_pattern=r"blk\.4[4-6]\..*=CPU",
            ub=512,
            tb=3
        )
        all_results.append(res)

    # Next test Candidate 1 (Generation Profile: blk.44-45 CPU, ub384, tb3)
    for p_size in prompt_targets:
        res = run_real_prompt_test(
            name="Candidate 1 (blk.44-45 CPU, ub384, tb3)",
            target_prompt_tokens=p_size,
            ot_pattern=r"blk\.4[4-5]\..*=CPU",
            ub=384,
            tb=3
        )
        all_results.append(res)

    clean_vram()

    # Save to JSON
    with open(r"K:\Project\Tests\hardware\real_prompt_sweep_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Print summary
    print("\n" + "=" * 115)
    print(f"{'Profile':<40} | {'Prompt':<7} | {'Status':<8} | {'PP (t/s)':<9} | {'TTFT':<7} | {'TG (t/s)':<8} | {'VRAM0 Free':<11} | {'VRAM1 Free':<11}")
    print("-" * 115)
    for r in all_results:
        p_tok = f"{r['prompt_tokens']//1000}K"
        pp = f"{r['pp_tps']:.1f}" if r['pp_tps'] else "—"
        ttft = f"{r['ttft_s']:.1f}s" if r['ttft_s'] else "—"
        tg = f"{r['tg_tps']:.1f}" if r['tg_tps'] else "—"
        f0 = f"{r['vram0_free']} MB"
        f1 = f"{r['vram1_free']} MB"
        print(f"{r['name']:<40} | {p_tok:<7} | {r['status']:<8} | {pp:<9} | {ttft:<7} | {tg:<8} | {f0:<11} | {f1:<11}")
    print("=" * 115)

if __name__ == "__main__":
    main()
