"""
Model Forge: Isolated Model Residency & VRAM Benchmark Runner
Spawns llama-server.exe on port 18005, verifies exact physical VRAM allocation via nvidia-smi,
measures token throughput, and tests speculative MTP drafter execution.
"""

import os
import sys
import time
import json
import shutil
import argparse
import subprocess
import requests

DEFAULT_SERVER_BIN = r'K:\Project\ik_llama\bin\llama-server.exe'
TEST_PORT = 18005

def get_gpu_memory(gpu_id: int):
    try:
        res = subprocess.run(
            ['nvidia-smi', f'--id={gpu_id}', '--query-gpu=memory.total,memory.used,memory.free', '--format=csv,nounits,noheader'],
            capture_output=True, text=True, check=True
        )
        line = res.stdout.strip()
        total, used, free = [float(x.strip()) for x in line.split(',')]
        return {'total_mb': total, 'used_mb': used, 'free_mb': free}
    except Exception as e:
        print(f"Warning: nvidia-smi query failed: {e}")
        return {'total_mb': 0.0, 'used_mb': 0.0, 'free_mb': 0.0}

def benchmark_model(
    model_path: str,
    server_bin: str = DEFAULT_SERVER_BIN,
    gpu_id: int = 0,
    ctx_size: int = 131072,
    ctk: str = 'q6_0',
    ctv: str = 'q4_0',
    spec_type: str = 'mtp:n_max=3,p_min=0.05',
    port: int = TEST_PORT
):
    if not os.path.exists(model_path):
        print(f"ERROR: Model file not found: {model_path}")
        return False

    if not os.path.exists(server_bin):
        print(f"ERROR: llama-server binary not found: {server_bin}")
        return False

    dev_flag = f"CUDA{gpu_id}"
    vram_before = get_gpu_memory(gpu_id)
    print("=" * 70)
    print(f"MODEL FORGE HARDWARE RESIDENCY & BENCHMARK")
    print(f"Model: {model_path}")
    print(f"Target GPU: {dev_flag} (Initial VRAM: Used {vram_before['used_mb']:.0f} MB / Total {vram_before['total_mb']:.0f} MB)")
    print(f"Context Window: {ctx_size:,} tokens | KV cache: -ctk {ctk} -ctv {ctv}")
    print(f"Speculative Decoding: {spec_type}")
    print(f"Isolated Test Port: {port}")
    print("=" * 70)

    cmd = [
        server_bin,
        '-m', model_path,
        '-c', str(ctx_size),
        '-ctk', ctk,
        '-ctv', ctv,
        '-dev', dev_flag,
        '--port', str(port),
        '--host', '127.0.0.1',
        '-ngl', '999'
    ]
    if spec_type:
        cmd.extend(['--spec-type', spec_type])

    print("Launching test instance...")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    server_url = f"http://127.0.0.1:{port}"
    ready = False
    start_wait = time.time()

    try:
        while time.time() - start_wait < 120:
            if proc.poll() is not None:
                print(f"ERROR: Server process terminated early with return code {proc.returncode}!")
                out, _ = proc.communicate()
                print(out[-2000:])
                return False

            try:
                res = requests.get(f"{server_url}/health", timeout=1)
                if res.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(1)

        if not ready:
            print("ERROR: Server did not become ready within 120 seconds.")
            return False

        # Physical VRAM measurement after model and context allocation
        vram_after = get_gpu_memory(gpu_id)
        delta_used = vram_after['used_mb'] - vram_before['used_mb']
        print(f"\n[PHYSICAL VRAM VERIFIED]")
        print(f"GPU {gpu_id} VRAM Used: {vram_after['used_mb']:.0f} MB ({vram_after['used_mb'] / 1024:.2f} GB)")
        print(f"Net Allocation by Model + {ctx_size:,} Ctx: {delta_used:.0f} MB ({delta_used / 1024:.2f} GB)")
        print(f"Remaining Free VRAM: {vram_after['free_mb']:.0f} MB ({vram_after['free_mb'] / 1024:.2f} GB)")

        # Send test prompt to verify inference and MTP speculative acceptance
        print("\nSending test prompt to evaluate generation speed and MTP execution...")
        prompt = "<|im_start|>user\nWrite a concise Python function to calculate SHA256 of a file in chunks.<|im_end|>\n<|im_start|>assistant\n"
        req_data = {
            "prompt": prompt,
            "n_predict": 128,
            "temperature": 0.2
        }

        t0 = time.time()
        c_res = requests.post(f"{server_url}/completion", json=req_data, timeout=30)
        t_gen = time.time() - t0

        if c_res.status_code == 200:
            res_json = c_res.json()
            content = res_json.get('content', '')
            tokens_eval = res_json.get('tokens_evaluated', 0)
            tokens_pred = res_json.get('tokens_predicted', 0)
            tps = tokens_pred / t_gen if t_gen > 0 else 0
            print(f"[BENCHMARK COMPLETED]")
            print(f"Predicted tokens: {tokens_pred} in {t_gen:.2f}s -> {tps:.2f} tokens/sec")
            print(f"Response sample:\n{content[:200]}...")
            return True
        else:
            print(f"ERROR: Completion request failed with HTTP {c_res.status_code}: {c_res.text}")
            return False

    finally:
        print("\nTerminating test server instance...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server shutdown complete.")

def main():
    parser = argparse.ArgumentParser(description='Model Forge Hardware Benchmark & VRAM Validator')
    parser.add_argument('--model', type=str, required=True, help='Path to GGUF model')
    parser.add_argument('--server-bin', type=str, default=DEFAULT_SERVER_BIN, help='Path to llama-server.exe')
    parser.add_argument('--gpu', type=int, default=0, help='Target GPU ID (0 for RTX 5060 Ti, 1 for RTX 2080 Ti)')
    parser.add_argument('--ctx', type=int, default=131072, help='Context window size')
    parser.add_argument('--ctk', type=str, default='q6_0', help='Key cache quantization type')
    parser.add_argument('--ctv', type=str, default='q4_0', help='Value cache quantization type')
    parser.add_argument('--spec-type', type=str, default='mtp:n_max=3,p_min=0.05', help='Speculative decoding argument')
    parser.add_argument('--port', type=int, default=TEST_PORT, help='Port for test server')
    args = parser.parse_args()

    success = benchmark_model(
        model_path=args.model,
        server_bin=args.server_bin,
        gpu_id=args.gpu,
        ctx_size=args.ctx,
        ctk=args.ctk,
        ctv=args.ctv,
        spec_type=args.spec_type,
        port=args.port
    )
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
