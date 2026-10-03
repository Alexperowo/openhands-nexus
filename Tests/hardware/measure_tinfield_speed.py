#!/usr/bin/env python3
"""
Tests/hardware/measure_tinfield_speed.py
Precise measurement of Prompt Processing (PP) and Text Generation (TG) speeds
comparing Baseline (mmap) vs Direct I/O (--load-mode dio).
"""

import sys
import time
import subprocess
import re
import psutil

LLAMA_CLI = r"K:\Project\llama-mainline\b11194\llama-cli.exe"
MODEL_PATH = r"D:\AI\Models\Tinfield-1-Mini\tinfield-1-mini-00001-of-00006.gguf"
VRAM_MANAGER = r"K:\Project\Config\vram_manager.py"

PROMPT = (
    "Explain the internal mechanics of Linux virtual memory subsystem: "
    "specifically how page cache, slab allocator, anonymous memory pages, "
    "and kswapd interact during severe memory pressure. Be concise and technical."
)

def clean_vram():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Stop-Process -Name llama-cli, llama-server -Force -ErrorAction SilentlyContinue"],
        timeout=10
    )
    subprocess.run([sys.executable, VRAM_MANAGER, "--wait-free", "1200", "--timeout", "10"], timeout=15)
    time.sleep(2)

def run_test(name: str, extra_args: list):
    clean_vram()
    print(f"\n=======================================================", flush=True)
    print(f"[*] RUNNING: {name}", flush=True)
    print(f"    Args: {' '.join(extra_args) if extra_args else '(Baseline mmap)'}", flush=True)
    print(f"=======================================================", flush=True)

    cmd = [
        LLAMA_CLI,
        "-m", MODEL_PATH,
        "-c", "4096",
        "-ngl", "999",
        "-dev", "CUDA0,CUDA1",
        "-ts", "12.2,19.4",
        "-ot", r"blk\.4[4-6]\..*=CPU",
        "-ctk", "q8_0",
        "-ctv", "q4_0",
        "-fa", "on",
        "-t", "6",
        "-p", PROMPT,
        "-n", "40",
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

    peak_ram = 0
    try:
        p_obj = psutil.Process(proc.pid)
    except Exception:
        p_obj = None

    while proc.poll() is None:
        if time.time() - t_start > 120:
            print("[!] Timeout 120s exceeded, killing proc...", flush=True)
            proc.kill()
            break
        try:
            if p_obj and p_obj.is_running():
                rss = p_obj.memory_info().rss
                if rss > peak_ram:
                    peak_ram = rss
        except Exception:
            pass
        time.sleep(0.15)

    stdout, _ = proc.communicate()
    elapsed = time.time() - t_start

    # Look for [ Prompt: XX.X t/s | Generation: YY.Y t/s ]
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

def main():
    res_baseline = run_test("Baseline (mmap)", [])
    res_dio = run_test("Direct I/O (--load-mode dio)", ["--load-mode", "dio"])

    clean_vram()

    print("\n" + "=" * 75)
    print(f"{'Mode':<30} | {'Peak RAM':<10} | {'Prompt Speed':<14} | {'Gen Speed':<12}")
    print("-" * 75)
    for r in [res_baseline, res_dio]:
        p_str = f"{r['prompt_tps']:.2f} t/s" if r['prompt_tps'] else "N/A"
        g_str = f"{r['gen_tps']:.2f} t/s" if r['gen_tps'] else "N/A"
        ram_str = f"{r['peak_ram_gb']:.2f} GB"
        print(f"{r['name']:<30} | {ram_str:<10} | {p_str:<14} | {g_str:<12}")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    main()
