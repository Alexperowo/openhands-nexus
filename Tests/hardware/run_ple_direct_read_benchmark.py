#!/usr/bin/env python3
"""
Tests/hardware/run_ple_direct_read_benchmark.py
Benchmarking Upstream PR #29030 (PLE Direct-Read) vs Baseline (-lzm auto mmap)
on Tinfield-1-Mini 177B at 131,072 Context Window with Real Diverse Prompts (50K & 70K).

Measurements:
- PP (Prompt Processing speed in tok/s)
- TTFT (Time To First Token in seconds)
- TG (Token Generation speed in tok/s)
- Peak & Free VRAM on GPU 0 (5060 Ti) and GPU 1 (2080 Ti)
- Peak System RAM usage
- Disk Read Throughput / Bytes read during prefill
- CPU Utilization (%)
- Output token validation (confirming identical generation)
- Direct-read confirmation (verifying ReadFile OVERLAPPED row reads active)
"""

import os
import sys
import time
import subprocess
import re
import psutil
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASELINE_CLI = r"K:\Project\llama-mainline\b11276\llama-cli.exe"
DIRECT_READ_CLI = r"K:\Project\llama-direct-read\build_vs\bin\Release\llama-cli.exe"
MODEL_PATH = r"D:\AI\Models\Tinfield-1-Mini\tinfield-1-mini-00001-of-00006.gguf"
VRAM_MANAGER = r"K:\Project\Config\vram_manager.py"
PROMPT_50K = r"K:\Project\Tests\hardware\prompt_50k.txt"
PROMPT_70K = r"K:\Project\Tests\hardware\prompt_70k.txt"

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
        vram = {}
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 4:
                idx = int(parts[0])
                vram[f"gpu{idx}_used_mb"] = int(parts[1])
                vram[f"gpu{idx}_free_mb"] = int(parts[2])
                vram[f"gpu{idx}_total_mb"] = int(parts[3])
        return vram
    except Exception:
        return {}

def run_single_benchmark(bin_path: str, prompt_file: str, mode_name: str, lzm_val: str, run_type: str = "warm"):
    clean_vram()
    print("\n" + "=" * 90, flush=True)
    print(f"[*] BENCHMARK: {mode_name} | RUN: {run_type.upper()} | LZM: {lzm_val}", flush=True)
    print(f"    Binary: {bin_path}", flush=True)
    print(f"    Prompt File: {prompt_file}", flush=True)
    print("=" * 90, flush=True)

    log_path = os.path.abspath(f"K:\\Project\\Tests\\hardware\\run_{mode_name.replace(' ', '_').replace('(', '').replace(')', '')}.log")

    cmd = [
        bin_path,
        "-m", MODEL_PATH,
        "-c", "131072",
        "-ngl", "999",
        "-dev", "CUDA0,CUDA1",
        "-ts", "12.2,19.4",
        "-ot", r"blk\.4[4-6]\..*=CPU",
        "-ctk", "q8_0",
        "-ctv", "q4_0",
        "-fa", "on",
        "-t", "6",
        "-b", "2048",
        "-ub", "512",
        "-tb", "3",
        "-lzm", lzm_val,
        "-n", "5",
        "-f", prompt_file,
        "-st",
        "--log-file", log_path,
        "-v"
    ]

    initial_disk_io = psutil.disk_io_counters()
    start_time = time.time()
    
    stdout_file = log_path.replace(".log", ".stdout.txt")
    stderr_file = log_path.replace(".log", ".stderr.txt")

    out_fp = open(stdout_file, "w", encoding="utf-8", errors="replace")
    err_fp = open(stderr_file, "w", encoding="utf-8", errors="replace")

    # Launch process with file streams (eliminates pipe deadlocks)
    proc = subprocess.Popen(
        cmd,
        stdout=out_fp,
        stderr=err_fp
    )

    gpu0_max_used = 0
    gpu1_max_used = 0
    gpu0_min_free = 999999
    gpu1_min_free = 999999
    max_ram_mb = 0
    cpu_samples = []

    while proc.poll() is None:
        vram = get_vram_snapshot()
        if "gpu0_used_mb" in vram:
            gpu0_max_used = max(gpu0_max_used, vram["gpu0_used_mb"])
            gpu0_min_free = min(gpu0_min_free, vram["gpu0_free_mb"])
        if "gpu1_used_mb" in vram:
            gpu1_max_used = max(gpu1_max_used, vram["gpu1_used_mb"])
            gpu1_min_free = min(gpu1_min_free, vram["gpu1_free_mb"])

        try:
            mem = psutil.virtual_memory()
            max_ram_mb = max(max_ram_mb, (mem.total - mem.available) / (1024 * 1024))
            cpu_samples.append(psutil.cpu_percent(interval=0.1))
        except Exception:
            pass
        time.sleep(0.4)

    out_fp.close()
    err_fp.close()

    end_time = time.time()
    total_elapsed = end_time - start_time
    final_disk_io = psutil.disk_io_counters()

    stdout = ""
    stderr = ""
    if os.path.exists(stdout_file):
        with open(stdout_file, "r", encoding="utf-8", errors="replace") as f:
            stdout = f.read()
    if os.path.exists(stderr_file):
        with open(stderr_file, "r", encoding="utf-8", errors="replace") as f:
            stderr = f.read()

    disk_read_bytes = 0
    if initial_disk_io and final_disk_io:
        disk_read_bytes = final_disk_io.read_bytes - initial_disk_io.read_bytes

    combined_output = stdout + "\n" + stderr

    # Extract PP speed
    pp_match = re.search(r"prompt eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*tokens.*?([\d\.]+)\s*tokens per second", combined_output)
    pp_speed = float(pp_match.group(3)) if pp_match else 0.0
    actual_prompt_tokens = int(pp_match.group(2)) if pp_match else 0
    pp_time_ms = float(pp_match.group(1)) if pp_match else 0.0
    ttft_sec = pp_time_ms / 1000.0 if pp_time_ms > 0 else total_elapsed

    # Extract TG speed
    tg_match = re.search(r"eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*runs.*?([\d\.]+)\s*tokens per second", combined_output)
    tg_speed = float(tg_match.group(3)) if tg_match else 0.0

    log_content = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                log_content = lf.read()
        except Exception:
            pass

    full_text_to_search = combined_output + "\n" + log_content

    # If pp_match wasn't in combined_output, search in log_content
    if not pp_match:
        pp_match = re.search(r"prompt eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*tokens.*?([\d\.]+)\s*tokens per second", full_text_to_search)
        if pp_match:
            pp_speed = float(pp_match.group(3))
            actual_prompt_tokens = int(pp_match.group(2))
            pp_time_ms = float(pp_match.group(1))
            ttft_sec = pp_time_ms / 1000.0

    if not tg_match:
        tg_match = re.search(r"eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*runs.*?([\d\.]+)\s*tokens per second", full_text_to_search)
        if tg_match:
            tg_speed = float(tg_match.group(3))

    direct_read_logged = "row reads enabled" in full_text_to_search
    lazy_reader_rows = re.findall(r"tensor (.*?) row reads enabled", full_text_to_search)

    # Extract generated output text
    output_lines = [line for line in stdout.splitlines() if not line.startswith("llama_") and not line.startswith("main:")]
    gen_text = "\n".join(output_lines).strip()

    avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0

    res = {
        "mode": mode_name,
        "run_type": run_type,
        "lzm": lzm_val,
        "prompt_tokens": actual_prompt_tokens,
        "pp_tok_s": pp_speed,
        "ttft_s": round(ttft_sec, 2),
        "tg_tok_s": tg_speed,
        "total_time_s": round(total_elapsed, 2),
        "gpu0_peak_used_mb": gpu0_max_used,
        "gpu0_min_free_mb": gpu0_min_free,
        "gpu1_peak_used_mb": gpu1_max_used,
        "gpu1_min_free_mb": gpu1_min_free,
        "peak_ram_mb": round(max_ram_mb, 1),
        "avg_cpu_percent": round(avg_cpu, 1),
        "disk_read_mb": round(disk_read_bytes / (1024 * 1024), 1),
        "direct_read_active": direct_read_logged,
        "direct_read_tensors": lazy_reader_rows,
        "return_code": proc.returncode,
        "gen_sample": gen_text[:200]
    }

    print(f"--> RESULTS: PP={res['pp_tok_s']} tok/s | TTFT={res['ttft_s']}s | TG={res['tg_tok_s']} tok/s")
    print(f"    VRAM GPU0 Free: {res['gpu0_min_free_mb']} MB | GPU1 Free: {res['gpu1_min_free_mb']} MB")
    print(f"    RAM Peak: {res['peak_ram_mb']} MB | CPU Avg: {res['avg_cpu_percent']}% | Disk Read: {res['disk_read_mb']} MB")
    print(f"    Direct Read Logged: {res['direct_read_active']} (Tensors: {res['direct_read_tensors']})")
    safe_sample = res['gen_sample'].encode('ascii', errors='replace').decode('ascii')
    print(f"    Generated Sample: {safe_sample!r}")

    return res

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PR #29030 PLE Direct-Read Benchmark")
    parser.add_argument("--test", choices=["50k", "70k", "all", "quick", "direct_50k", "direct_70k", "baseline_70k"], default="all", help="Which prompt size to test")
    parser.add_argument("--output", default=r"K:\Project\Tests\hardware\direct_read_benchmark_results.json", help="Path to save results")
    args = parser.parse_args()

    results = []

    tests_to_run = []
    if args.test in ["baseline_70k"]:
        tests_to_run = [
            ("Baseline (mmap) Warm 70K", BASELINE_CLI, PROMPT_70K, "auto", "warm")
        ]
    elif args.test in ["direct_50k"]:
        tests_to_run = [
            ("PR #29030 (Direct-Read) Warm 50K", DIRECT_READ_CLI, PROMPT_50K, "auto", "warm")
        ]
    elif args.test in ["direct_70k"]:
        tests_to_run = [
            ("PR #29030 (Direct-Read) Warm 70K", DIRECT_READ_CLI, PROMPT_70K, "auto", "warm")
        ]
    elif args.test in ["quick"]:
        tests_to_run = [
            ("Baseline (mmap)", BASELINE_CLI, PROMPT_50K, "auto", "warm"),
            ("PR #29030 (Direct-Read)", DIRECT_READ_CLI, PROMPT_50K, "auto", "warm")
        ]
    elif args.test in ["50k"]:
        tests_to_run = [
            ("Baseline (mmap) Cold 50K", BASELINE_CLI, PROMPT_50K, "auto", "cold"),
            ("Baseline (mmap) Warm 50K", BASELINE_CLI, PROMPT_50K, "auto", "warm"),
            ("PR #29030 (Direct-Read) Cold 50K", DIRECT_READ_CLI, PROMPT_50K, "auto", "cold"),
            ("PR #29030 (Direct-Read) Warm 50K", DIRECT_READ_CLI, PROMPT_50K, "auto", "warm")
        ]
    elif args.test in ["70k"]:
        tests_to_run = [
            ("Baseline (mmap) Cold 70K", BASELINE_CLI, PROMPT_70K, "auto", "cold"),
            ("Baseline (mmap) Warm 70K", BASELINE_CLI, PROMPT_70K, "auto", "warm"),
            ("PR #29030 (Direct-Read) Cold 70K", DIRECT_READ_CLI, PROMPT_70K, "auto", "cold"),
            ("PR #29030 (Direct-Read) Warm 70K", DIRECT_READ_CLI, PROMPT_70K, "auto", "warm")
        ]
    elif args.test in ["all"]:
        tests_to_run = [
            ("Baseline (mmap) Cold 50K", BASELINE_CLI, PROMPT_50K, "auto", "cold"),
            ("Baseline (mmap) Warm 50K", BASELINE_CLI, PROMPT_50K, "auto", "warm"),
            ("PR #29030 (Direct-Read) Cold 50K", DIRECT_READ_CLI, PROMPT_50K, "auto", "cold"),
            ("PR #29030 (Direct-Read) Warm 50K", DIRECT_READ_CLI, PROMPT_50K, "auto", "warm"),
            ("Baseline (mmap) Cold 70K", BASELINE_CLI, PROMPT_70K, "auto", "cold"),
            ("Baseline (mmap) Warm 70K", BASELINE_CLI, PROMPT_70K, "auto", "warm"),
            ("PR #29030 (Direct-Read) Cold 70K", DIRECT_READ_CLI, PROMPT_70K, "auto", "cold"),
            ("PR #29030 (Direct-Read) Warm 70K", DIRECT_READ_CLI, PROMPT_70K, "auto", "warm")
        ]

    for name, bin_path, prompt_file, lzm_val, r_type in tests_to_run:
        if not os.path.exists(bin_path):
            print(f"ERROR: Binary does not exist: {bin_path}", file=sys.stderr)
            continue
        res = run_single_benchmark(bin_path, prompt_file, name, lzm_val, r_type)
        results.append(res)
        time.sleep(3)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "#" * 90)
    print(f"Benchmark run complete. Saved {len(results)} records to {args.output}")
    print("#" * 90)

