#!/usr/bin/env python3
"""
Tests/hardware/quick_tinfield_pp_test.py
Empirical A/B testing of Tinfield Prompt Processing (PP) bottlenecks:
- Lazy mode (-lzm auto vs -lzm off)
- Ubatch size (-ub 128, 256, 512, 1024)
- Tensor-level offload (-ot)
- Thread batching (-tb 2, 3, 4)
Using prompt length = 2048 tokens.
"""

import sys
import time
import subprocess
import re
import psutil

LLAMA_CLI = r"K:\Project\llama-mainline\b11276\llama-cli.exe"
MODEL_PATH = r"D:\AI\Models\Tinfield-1-Mini\tinfield-1-mini-00001-of-00006.gguf"
VRAM_MANAGER = r"K:\Project\Config\vram_manager.py"

# Realistic code/text prompt replicated to reach ~2048 tokens
SAMPLE_TEXT = (
    "In systems engineering, optimizing kernel page cache eviction and direct memory access (DMA) "
    "across heterogeneous PCIe topologies requires careful consideration of non-uniform memory access (NUMA), "
    "translation lookaside buffer (TLB) shootdowns, and hardware cache coherence protocols. "
    "When a GPU offloads tensor layers back to system DRAM over a limited PCIe 4.0 x4 link, "
    "the bottleneck shifts from GPU memory bandwidth to host-to-device (H2D) and device-to-host (D2H) transfer latencies. "
)
# ~50 words per repeat -> 40 repeats ~ 2000 tokens
PROMPT_2K = SAMPLE_TEXT * 40

def clean_vram():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Stop-Process -Name llama-cli, llama-server -Force -ErrorAction SilentlyContinue"],
        timeout=10
    )
    subprocess.run([sys.executable, VRAM_MANAGER, "--wait-free", "1200", "--timeout", "10"], timeout=15)
    time.sleep(2)

def run_pp_bench(name: str, cli_args: list):
    clean_vram()
    print(f"\n" + "=" * 70, flush=True)
    print(f"[*] TEST: {name}", flush=True)
    print(f"    Args: {' '.join(cli_args)}", flush=True)
    print("=" * 70, flush=True)

    base_cmd = [
        LLAMA_CLI,
        "-m", MODEL_PATH,
        "-c", "8192",
        "-ngl", "999",
        "-dev", "CUDA0,CUDA1",
        "-ts", "12.2,19.4",
        "-ctk", "q8_0",
        "-ctv", "q4_0",
        "-fa", "on",
        "-t", "6",
        "-b", "2048",
        "-n", "2",
        "-p", PROMPT_2K,
        "-st"
    ]
    full_cmd = base_cmd + cli_args

    t_start = time.time()
    proc = subprocess.Popen(
        full_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    peak_ram = 0
    try:
        p_obj = psutil.Process(proc.pid)
    except Exception:
        p_obj = None

    while proc.poll() is None:
        if time.time() - t_start > 180:
            print("[!] Timeout 180s exceeded, terminating proc...", flush=True)
            subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {proc.pid} -Force"])
            break
        try:
            if p_obj and p_obj.is_running():
                rss = p_obj.memory_info().rss
                if rss > peak_ram:
                    peak_ram = rss
        except Exception:
            pass
        time.sleep(0.2)

    stdout, _ = proc.communicate()
    elapsed = time.time() - t_start

    speed_match = re.search(r"\[\s*Prompt:\s*([\d\.]+)\s*t/s\s*\|\s*Generation:\s*([\d\.]+)\s*t/s\s*\]", stdout)
    prompt_tps = float(speed_match.group(1)) if speed_match else None
    gen_tps = float(speed_match.group(2)) if speed_match else None

    peak_ram_gb = peak_ram / (1024 ** 3)
    print(f"[+] Result for {name}:")
    print(f"    Exit code:        {proc.returncode}")
    print(f"    Elapsed:          {elapsed:.2f}s")
    print(f"    Peak RAM:         {peak_ram_gb:.2f} GB")
    print(f"    Prompt Eval (PP): {prompt_tps} t/s")
    print(f"    Generation (TG):  {gen_tps} t/s")

    return {
        "name": name,
        "success": proc.returncode == 0 and prompt_tps is not None,
        "peak_ram_gb": peak_ram_gb,
        "prompt_tps": prompt_tps,
        "gen_tps": gen_tps,
        "elapsed_s": elapsed
    }

if __name__ == "__main__":
    results = []

    # 1. Baseline: blk.44-45 CPU, ub 256, tb 3, lzm auto
    results.append(run_pp_bench(
        "Baseline (blk.44-45 CPU, ub256, tb3, lzm auto)",
        ["-ot", r"blk\.4[4-5]\..*=CPU", "-ub", "256", "-tb", "3"]
    ))

    # 2. PLE: lzm off (resident mmap in RAM)
    results.append(run_pp_bench(
        "PLE resident RAM (-lzm off, blk.44-45 CPU, ub256, tb3)",
        ["-ot", r"blk\.4[4-5]\..*=CPU", "-ub", "256", "-tb", "3", "-lzm", "off"]
    ))

    # 3. Expert-only offload: blk.44-45 ffn_exps only, ub 256, tb 3
    results.append(run_pp_bench(
        "Expert-only (-ot ffn_exps, ub256, tb3)",
        ["-ot", r"blk\.4[4-5]\.ffn_.*exps\..*=CPU", "-ub", "256", "-tb", "3"]
    ))

    # 4. Ubatch scaling on expert-only
    for ub in [384, 512, 1024]:
        results.append(run_pp_bench(
            f"Expert-only ub={ub} (tb3)",
            ["-ot", r"blk\.4[4-5]\.ffn_.*exps\..*=CPU", "-ub", str(ub), "-tb", "3"]
        ))

    # 5. Thread batching on expert-only
    for tb in [2, 4]:
        results.append(run_pp_bench(
            f"Expert-only tb={tb} (ub512)",
            ["-ot", r"blk\.4[4-5]\.ffn_.*exps\..*=CPU", "-ub", "512", "-tb", str(tb)]
        ))

    # 6. Single-block offload: blk.44 CPU only
    results.append(run_pp_bench(
        "Single-block CPU (blk.44 CPU, ub512, tb3)",
        ["-ot", r"blk\.44\..*=CPU", "-ub", "512", "-tb", "3"]
    ))

    print("\n" + "=" * 80)
    print(f"{'Configuration':<45} | {'PP (t/s)':<10} | {'TG (t/s)':<10} | {'RAM (GB)':<10}")
    print("-" * 80)
    for r in results:
        pp_str = f"{r['prompt_tps']:.1f}" if r['prompt_tps'] else "FAIL"
        tg_str = f"{r['gen_tps']:.1f}" if r['gen_tps'] else "FAIL"
        ram_str = f"{r['peak_ram_gb']:.2f}"
        print(f"{r['name']:<45} | {pp_str:<10} | {tg_str:<10} | {ram_str:<10}")
    print("=" * 80)
