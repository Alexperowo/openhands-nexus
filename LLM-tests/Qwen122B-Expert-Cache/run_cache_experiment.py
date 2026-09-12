import subprocess
import time
import os
import sys
import json
import urllib.request
import psutil

# Import benchmark functions from harness
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_harness import run_benchmark_suite, get_gpu_memory, get_system_ram

MODEL_PATH = r"K:\Project\Models\Qwen-122b\Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf"
SERVER_BIN = r"K:\Project\LLM-tests\Qwen122B-Expert-Cache\bin\llama-server.exe"

def wait_for_server_ready(port, timeout_sec=180):
    url = f"http://127.0.0.1:{port}/health"
    start = time.time()
    print(f"Waiting for server on port {port} to become ready...", flush=True)
    while time.time() - start < timeout_sec:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == "ok" or data.get("status") == "loading model" or "status" in data:
                        if data.get("status") == "ok":
                            print(f"Server is READY! (took {round(time.time()-start, 1)}s)")
                            return True
                        else:
                            print(f"Server status: {data.get('status')}...", flush=True)
        except Exception:
            pass
        time.sleep(2)
    print("Server failed to report ready within timeout!")
    return False

def run_cache_experiment(exp_id, cache_slots=0, cache_inserts=2, port=5804, ngl=49, ctx=16384, tensor_split="12,26"):
    log_dir = r"K:\Project\LLM-tests\Qwen122B-Expert-Cache\logs"
    results_dir = r"K:\Project\LLM-tests\Qwen122B-Expert-Cache\results"
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    
    server_log_file = os.path.join(log_dir, f"server_{exp_id}.log")
    override_arg = r"blk\.(3[3-9]|4[0-7])\.ffn_(up|gate|down)_exps=CPU"
    
    cmd = [
        SERVER_BIN,
        "-m", MODEL_PATH,
        "-c", str(ctx),
        "-ngl", str(ngl),
        "-ot", override_arg,
        "-dev", "CUDA0,CUDA1",
        "-sm", "layer",
        "-ts", tensor_split,
        "-ctk", "q5_0",
        "-ctv", "q4_0",
        "-fa", "on",
        "-t", "6",
        "-np", "1",
        "-lv", "4",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--temp", "0.6",
        "--top-p", "0.95",
        "--moe-expert-cache", str(cache_slots),
        "--moe-expert-cache-inserts", str(cache_inserts),
        "--jinja"
    ]
    
    print(f"\n==================================================================")
    print(f"Starting Experiment: {exp_id}")
    print(f"Cache Slots: {cache_slots} | Cache Inserts: {cache_inserts} | NGL: {ngl} | Port: {port}")
    print(f"Command: {' '.join(cmd)}")
    print(f"==================================================================\n")
    
    with open(server_log_file, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            cmd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(SERVER_BIN)
        )
        
    try:
        ready = wait_for_server_ready(port, timeout_sec=240)
        if not ready:
            print(f"ERROR: Server failed to start for {exp_id}. Check log: {server_log_file}")
            proc.terminate()
            return None
            
        print(f"Server PID: {proc.pid}. Running benchmark suite...")
        time.sleep(3) # Let VRAM settle
        
        endpoint_url = f"http://127.0.0.1:{port}"
        suite_res = run_benchmark_suite(
            experiment_id=exp_id,
            endpoint_url=endpoint_url,
            model_name="qwen122",
            output_dir=results_dir,
            runs_per_task=2
        )
        
        # Append cache configuration to result
        suite_res["cache_config"] = {
            "cache_slots": cache_slots,
            "cache_inserts": cache_inserts,
            "ngl": ngl,
            "ctx": ctx,
            "split_mode": "layer",
            "tensor_split": tensor_split,
            "override_arg": override_arg
        }
        
        # Parse cache metrics from server log
        cache_log_lines = []
        try:
            with open(server_log_file, "r", encoding="utf-8", errors="ignore") as lf:
                for line in lf:
                    if "MoE expert cache" in line or "moe-cache:" in line:
                        cache_log_lines.append(line.strip())
        except Exception as e:
            cache_log_lines.append(f"Error reading log: {e}")
            
        suite_res["cache_log_lines"] = cache_log_lines
        
        # Resave enriched results
        out_file = os.path.join(results_dir, f"{exp_id}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(suite_res, f, indent=2, ensure_ascii=False)
            
        print(f"Experiment {exp_id} COMPLETED successfully!")
        return suite_res
        
    finally:
        print(f"Terminating server PID {proc.pid}...", end="", flush=True)
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        print(" Terminated.")
        time.sleep(3)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp-id", required=True)
    parser.add_argument("--cache-slots", type=int, default=0)
    parser.add_argument("--cache-inserts", type=int, default=2)
    parser.add_argument("--port", type=int, default=5804)
    parser.add_argument("--ngl", type=int, default=49)
    parser.add_argument("--tensor-split", type=str, default="12,26")
    parser.add_argument("--ctx", type=int, default=16384)
    args = parser.parse_args()
    
    run_cache_experiment(
        exp_id=args.exp_id,
        cache_slots=args.cache_slots,
        cache_inserts=args.cache_inserts,
        port=args.port,
        ngl=args.ngl,
        ctx=args.ctx,
        tensor_split=args.tensor_split
    )
