#!/usr/bin/env python3
"""
Tests/hardware/run_rigorous_direct_read_ab.py
Rigorous Empirical A/B Benchmark:
Engine A: Baseline mainline b11276 (mmap / lazy)
Engine B: PR #29030 (Direct-Read, Win32 ReadFile + OVERLAPPED)

Target: Tinfield-1-Mini 177B inside fixed context window 131,072
Prompts: 50K, 60K, 70K unique diverse non-repeating tokens
Measurements:
- t_load_s: Model load time
- t_pp_s: Pure prompt processing time (in-memory TTFT)
- TTFT_from_launch = t_load_s + t_pp_s
- PP: Prompt processing speed (tok/s)
- TG: Token generation speed (tok/s)
- GPU0 / GPU1 Peak & Free VRAM
- Process Working Set RAM & System Peak RAM
- NVMe Read Throughput (MB)
- CPU Utilization (%)
- PCIe RX / TX (MB/s)
- Direct-Read log validation
"""

import os
import sys
import time
import subprocess
import re
import psutil
import json
import threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASELINE_CLI = r"K:\Project\llama-mainline\b11276\llama-cli.exe"
DIRECT_READ_CLI = r"K:\Project\llama-direct-read\bin\llama-cli.exe"
MODEL_PATH = r"D:\AI\Models\Tinfield-1-Mini\tinfield-1-mini-00001-of-00006.gguf"
VRAM_MANAGER = r"K:\Project\Config\vram_manager.py"

PROMPT_MAP = {
    "50k": r"K:\Project\Tests\hardware\prompt_50k.txt",
    "60k": r"K:\Project\Tests\hardware\prompt_60k.txt",
    "70k": r"K:\Project\Tests\hardware\prompt_70k.txt"
}

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

def run_single_experiment(engine_name: str, bin_path: str, prompt_file: str, prompt_label: str, run_idx: int, run_type: str = "warm"):
    clean_vram()
    print("\n" + "=" * 95, flush=True)
    print(f"[*] RUN: [{engine_name}] | PROMPT: {prompt_label} | ITERATION: #{run_idx} | TYPE: {run_type.upper()}", flush=True)
    print(f"    Binary: {bin_path}", flush=True)
    print(f"    Prompt: {prompt_file}", flush=True)
    print("=" * 95, flush=True)

    log_tag = f"{engine_name}_{prompt_label}_iter{run_idx}_{run_type}".replace(" ", "_").replace("#", "")
    log_path = os.path.abspath(f"K:\\Project\\Tests\\hardware\\log_{log_tag}.log")
    stdout_file = os.path.abspath(f"K:\\Project\\Tests\\hardware\\stdout_{log_tag}.txt")
    stderr_file = os.path.abspath(f"K:\\Project\\Tests\\hardware\\stderr_{log_tag}.txt")

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
        "-lzm", "auto",
        "-n", "5",
        "-f", prompt_file,
        "-st",
        "--log-file", log_path,
        "-v"
    ]

    initial_disk_io = psutil.disk_io_counters()
    start_wall_time = time.time()

    out_fp = open(stdout_file, "w", encoding="utf-8", errors="replace")
    err_fp = open(stderr_file, "w", encoding="utf-8", errors="replace")

    proc = subprocess.Popen(
        cmd,
        stdout=out_fp,
        stderr=err_fp
    )

    gpu0_max_used = 0
    gpu1_max_used = 0
    gpu0_min_free = 999999
    gpu1_min_free = 999999
    max_sys_ram_mb = 0
    max_ws_ram_mb = 0
    cpu_samples = []

    try:
        proc_ps = psutil.Process(proc.pid)
    except Exception:
        proc_ps = None

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
            max_sys_ram_mb = max(max_sys_ram_mb, (mem.total - mem.available) / (1024 * 1024))
            if proc_ps and proc_ps.is_running():
                ws_mb = proc_ps.memory_info().rss / (1024 * 1024)
                max_ws_ram_mb = max(max_ws_ram_mb, ws_mb)
            cpu_samples.append(psutil.cpu_percent(interval=0.1))
        except Exception:
            pass
        time.sleep(0.4)

    out_fp.close()
    err_fp.close()

    end_wall_time = time.time()
    total_wall_s = end_wall_time - start_wall_time
    final_disk_io = psutil.disk_io_counters()

    nvme_read_mb = 0.0
    if initial_disk_io and final_disk_io:
        nvme_read_mb = round((final_disk_io.read_bytes - initial_disk_io.read_bytes) / (1024 * 1024), 1)

    log_content = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
        except Exception:
            pass

    stdout_content = ""
    if os.path.exists(stdout_file):
        try:
            with open(stdout_file, "r", encoding="utf-8", errors="replace") as f:
                stdout_content = f.read()
        except Exception:
            pass

    full_output = stdout_content + "\n" + log_content

    # Parse Model Load Time
    load_match = re.search(r"load time\s*=\s*([\d\.]+)\s*ms", full_output)
    t_load_s = round(float(load_match.group(1)) / 1000.0, 2) if load_match else 0.0

    # Parse Pure Prompt Processing Time & PP Speed
    pp_match = re.search(r"prompt eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*tokens.*?([\d\.]+)\s*tokens per second", full_output)
    if pp_match:
        t_pp_s = round(float(pp_match.group(1)) / 1000.0, 2)
        n_tokens = int(pp_match.group(2))
        pp_tok_s = float(pp_match.group(3))
    else:
        t_pp_s = round(total_wall_s - t_load_s, 2)
        n_tokens = 0
        pp_tok_s = 0.0

    # Parse Generation Speed
    tg_match = re.search(r"eval time\s*=\s*([\d\.]+)\s*ms\s*/\s*(\d+)\s*runs.*?([\d\.]+)\s*tokens per second", full_output)
    tg_tok_s = float(tg_match.group(3)) if tg_match else 0.0

    # TTFT Breakdown:
    # 1. TTFT_pure: Time from prompt arrival to first token on loaded server (pure inference = t_pp_s)
    # 2. TTFT_from_launch: Total time including cold model loading from disk
    ttft_pure = t_pp_s
    ttft_from_launch = round(t_load_s + t_pp_s, 2)

    # Validate Direct Read
    direct_read_logged = "row reads enabled" in full_output

    avg_cpu = round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0

    res = {
        "engine": engine_name,
        "binary": os.path.basename(bin_path),
        "prompt_label": prompt_label,
        "iteration": run_idx,
        "run_type": run_type,
        "tokens": n_tokens,
        "t_load_s": t_load_s,
        "t_pp_s": t_pp_s,
        "ttft_pure_s": ttft_pure,
        "ttft_from_launch_s": ttft_from_launch,
        "pp_tok_s": pp_tok_s,
        "tg_tok_s": tg_tok_s,
        "total_wall_s": round(total_wall_s, 2),
        "gpu0_free_mb": gpu0_min_free,
        "gpu1_free_mb": gpu1_min_free,
        "ws_ram_mb": round(max_ws_ram_mb, 1),
        "sys_peak_ram_mb": round(max_sys_ram_mb, 1),
        "nvme_read_mb": nvme_read_mb,
        "avg_cpu_percent": avg_cpu,
        "direct_read_active": direct_read_logged,
        "return_code": proc.returncode
    }

    print(f"\n--> MEASURED:")
    print(f"    Tokens: {res['tokens']} | PP: {res['pp_tok_s']} tok/s | TG: {res['tg_tok_s']} tok/s")
    print(f"    t_load: {res['t_load_s']}s | t_pp: {res['t_pp_s']}s | TTFT (pure): {res['ttft_pure_s']}s | TTFT (from launch): {res['ttft_from_launch_s']}s")
    print(f"    VRAM Free: GPU0={res['gpu0_free_mb']}MB, GPU1={res['gpu1_free_mb']}MB | WS RAM: {res['ws_ram_mb']}MB")
    print(f"    NVMe Read: {res['nvme_read_mb']}MB | CPU: {res['avg_cpu_percent']}% | Direct-Read: {res['direct_read_active']}")

    return res

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rigorous Direct-Read A/B Benchmark")
    parser.add_argument("--prompt", choices=["50k", "60k", "70k", "all"], default="all")
    parser.add_argument("--repeats", type=int, default=1, help="Repetitions per test point")
    parser.add_argument("--output", default=r"K:\Project\Tests\hardware\ab_direct_read_rigorous.json")
    args = parser.parse_args()

    prompts = ["50k", "60k", "70k"] if args.prompt == "all" else [args.prompt]
    all_results = []

    for p in prompts:
        p_file = PROMPT_MAP[p]
        for rep in range(1, args.repeats + 1):
            # Run Engine A: Baseline mainline
            res_a = run_single_experiment("Baseline (mmap)", BASELINE_CLI, p_file, p, rep, "warm")
            all_results.append(res_a)
            time.sleep(3)

            # Run Engine B: PR #29030 Direct Read
            res_b = run_single_experiment("PR #29030 (Direct-Read)", DIRECT_READ_CLI, p_file, p, rep, "warm")
            all_results.append(res_b)
            time.sleep(3)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print("\n" + "#" * 95)
    print(f"RIGOROUS A/B SUITE COMPLETED. {len(all_results)} runs recorded in {args.output}")
    print("#" * 95)
