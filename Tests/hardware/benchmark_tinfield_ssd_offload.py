#!/usr/bin/env python3
"""
Tests/hardware/benchmark_tinfield_ssd_offload.py

Empirical benchmark comparing:
1. Baseline: Current mmap + CPU layer offload (-ot "blk\.4[4-6]\..*=CPU")
2. Lazy Mode: Streaming tensor rows from SSD on demand (-lzm on)
3. Direct I/O / No-MMap: (--load-mode dio or --load-mode none)

Measures:
- Peak RAM WorkingSet (MB / GB)
- Peak GPU 0 & GPU 1 VRAM (MB)
- Load time (s)
- Generation speed (tokens/sec)
"""

import os
import sys
import time
import subprocess
import re
import psutil

LLAMA_CLI = r"K:\Project\llama-mainline\b11194\llama-cli.exe"
MODEL_PATH = r"D:\AI\Models\Tinfield-1-Mini\tinfield-1-mini-00001-of-00006.gguf"
VRAM_MANAGER = r"K:\Project\Config\vram_manager.py"

def get_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True
        )
        gpus = []
        for line in out.strip().splitlines():
            idx, used, total = [int(x.strip()) for x in line.split(",")]
            gpus.append({"index": idx, "used_mb": used, "total_mb": total})
        return gpus
    except Exception:
        return []

def clean_vram():
    print("[*] Reclaiming VRAM and stopping any active llama processes...", flush=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", "Stop-Process -Name llama-cli, llama-server -Force -ErrorAction SilentlyContinue"], timeout=10)
    subprocess.run([sys.executable, VRAM_MANAGER, "--wait-free", "1200", "--timeout", "10"], timeout=15)
    time.sleep(2)

def run_benchmark_case(name: str, extra_args: list, ctx_size: int = 16384, gen_tokens: int = 25):
    print("\n" + "=" * 70, flush=True)
    print(f"[*] BENCHMARK CONFIGURATION: {name}", flush=True)
    print(f"    Extra args: {' '.join(extra_args) if extra_args else '(None - Baseline)'}", flush=True)
    print("=" * 70, flush=True)

    clean_vram()
    gpus_before = get_vram()
    vram_before_str = ", ".join([f"GPU{g['index']}: {g['used_mb']}MB" for g in gpus_before])
    print(f"  VRAM before: {vram_before_str}", flush=True)

    cmd = [
        LLAMA_CLI,
        "-m", MODEL_PATH,
        "-c", str(ctx_size),
        "-ngl", "999",
        "-dev", "CUDA0,CUDA1",
        "-ts", "12.2,19.4",
        "-ot", r"blk\.4[4-6]\..*=CPU",
        "-ctk", "q8_0",
        "-ctv", "q4_0",
        "-fa", "on",
        "-t", "6",
        "-p", "Explain what an operating system kernel is in two concise sentences.",
        "-n", str(gen_tokens),
        "--temp", "0.2",
        "-st"
    ] + extra_args

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

    peak_ram_bytes = 0
    peak_vram_gpu0 = 0
    peak_vram_gpu1 = 0

    try:
        p_obj = psutil.Process(proc.pid)
    except Exception:
        p_obj = None

    while proc.poll() is None:
        if time.time() - t_start > 120:
            print("[!] Timeout reached (120s), terminating process...", flush=True)
            proc.kill()
            break
        try:
            if p_obj and p_obj.is_running():
                mem = p_obj.memory_info().rss
                if mem > peak_ram_bytes:
                    peak_ram_bytes = mem
        except Exception:
            pass

        gpus = get_vram()
        if len(gpus) >= 2:
            if gpus[0]["used_mb"] > peak_vram_gpu0:
                peak_vram_gpu0 = gpus[0]["used_mb"]
            if gpus[1]["used_mb"] > peak_vram_gpu1:
                peak_vram_gpu1 = gpus[1]["used_mb"]

        time.sleep(0.2)

    stdout, _ = proc.communicate()
    elapsed = time.time() - t_start

    # Extract performance metrics from llama_print_timings
    prompt_eval_match = re.search(r"prompt eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*tokens.*?([\d\.]+)\s*tokens per second", stdout)
    eval_match = re.search(r"eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*runs.*?([\d\.]+)\s*tokens per second", stdout)
    load_time_match = re.search(r"load time\s*=\s*([\d\.]+)\s*ms", stdout)

    prompt_tps = float(prompt_eval_match.group(3)) if prompt_eval_match else 0.0
    eval_tps = float(eval_match.group(3)) if eval_match else 0.0
    load_time_s = (float(load_time_match.group(1)) / 1000.0) if load_time_match else 0.0

    peak_ram_gb = peak_ram_bytes / (1024 ** 3)

    print(f"\n[+] RESULTS FOR: {name}")
    print(f"    Exit Code:        {proc.returncode}")
    print(f"    Total Wall Time:  {elapsed:.2f}s")
    print(f"    Model Load Time:  {load_time_s:.2f}s")
    print(f"    Peak Host RAM:    {peak_ram_gb:.2f} GB ({peak_ram_bytes / (1024**2):.1f} MB)")
    print(f"    Peak VRAM GPU0:   {peak_vram_gpu0} MB / 16311 MB")
    print(f"    Peak VRAM GPU1:   {peak_vram_gpu1} MB / 22528 MB")
    print(f"    Prompt Speed:     {prompt_tps:.2f} t/s")
    print(f"    Generation Speed: {eval_tps:.2f} t/s")

    # Check for errors in output if failed
    if proc.returncode != 0:
        print("\n[!] PROCESS ERROR OUTPUT:")
        error_lines = [l for l in stdout.splitlines() if "error" in l.lower() or "exception" in l.lower() or "failed" in l.lower()]
        for el in error_lines[-10:]:
            print(f"    {el}")

    return {
        "name": name,
        "success": proc.returncode == 0,
        "peak_ram_gb": peak_ram_gb,
        "peak_vram_gpu0": peak_vram_gpu0,
        "peak_vram_gpu1": peak_vram_gpu1,
        "load_time_s": load_time_s,
        "prompt_tps": prompt_tps,
        "eval_tps": eval_tps,
        "elapsed_s": elapsed
    }

def main():
    if not os.path.exists(MODEL_PATH):
        print(f"[-] Model not found at: {MODEL_PATH}")
        sys.exit(1)

    print("====================================================================")
    print("      TINFIELD 177B: EMPIRICAL RAM VS SSD OFFLOAD BENCHMARK        ")
    print("====================================================================")

    results = []

    # 1. Baseline: Current mmap + CPU layer offload
    r_baseline = run_benchmark_case(
        name="Baseline (Current Config: mmap + CPU Offload)",
        extra_args=[]
    )
    results.append(r_baseline)

    # 2. Lazy Mode on-demand tensor streaming
    r_lazy = run_benchmark_case(
        name="Lazy Mode (-lzm on: On-Demand Tensor Streaming)",
        extra_args=["-lzm", "on"]
    )
    results.append(r_lazy)

    # 3. Direct I/O loading
    r_dio = run_benchmark_case(
        name="Direct I/O (--load-mode dio)",
        extra_args=["--load-mode", "dio"]
    )
    results.append(r_dio)

    # Clean up after test
    clean_vram()

    # Print summary table
    print("\n" + "=" * 80)
    print(f"{'Configuration':<45} | {'Peak RAM':<10} | {'Load Time':<10} | {'Gen Speed':<10}")
    print("-" * 80)
    for r in results:
        status_str = f"{r['peak_ram_gb']:.2f} GB" if r['success'] else "FAILED"
        load_str = f"{r['load_time_s']:.2f}s" if r['success'] else "N/A"
        speed_str = f"{r['eval_tps']:.2f} t/s" if r['success'] else "N/A"
        print(f"{r['name']:<45} | {status_str:<10} | {load_str:<10} | {speed_str:<10}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
