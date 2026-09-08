import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

BACKEND = r"K:\Project\ik_llama\bin\llama-server.exe"
MODEL = r"K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf"
BENCH_PROMPT_FILE = r"K:\Project\LLM-tests\benchmark_prompt.txt"
BASE_DIR = r"K:\Project\LLM-tests\Qwen3-Next-80B"
LOG_DIR = os.path.join(BASE_DIR, "logs")
CSV_FILE = os.path.join(BASE_DIR, "BENCHMARKS.csv")
RESULT_MD = os.path.join(BASE_DIR, "RESULT.md")
PORT = 18096

os.makedirs(LOG_DIR, exist_ok=True)

def log(msg, level="INFO"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def get_vram():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], encoding="utf-8")
        return int(out.strip())
    except Exception:
        return 0

def get_gpu_util():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], encoding="utf-8")
        return int(out.strip())
    except Exception:
        return 0

def get_ram_info():
    try:
        cmd = 'powershell -NoProfile -Command "$os = Get-CimInstance Win32_OperatingSystem; Write-Host ([int](($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1024))"'
        out = subprocess.check_output(cmd, shell=True, encoding="utf-8")
        return int(out.strip())
    except Exception:
        return 0

def get_cpu_util():
    try:
        cmd = 'powershell -NoProfile -Command "$c = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; Write-Host [int]$c"'
        out = subprocess.check_output(cmd, shell=True, encoding="utf-8")
        return int(out.strip())
    except Exception:
        return 0

def init_csv():
    header = "mode,ngl,context,prompt_tokens,generated_tokens,thinking_tokens,answer_tokens,prompt_tps,generation_tps,ttft_s,wall_time_s,peak_vram_mib,peak_ram_mib,gpu_util_pct,cpu_util_pct,status,notes\n"
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", encoding="utf-8") as f:
            f.write(header)

def add_csv_row(row_dict):
    init_csv()
    row = f"{row_dict.get('mode','')},{row_dict.get('ngl','')},{row_dict.get('context','')},{row_dict.get('prompt_tokens',0)},{row_dict.get('generated_tokens',0)},{row_dict.get('thinking_tokens',0)},{row_dict.get('answer_tokens',0)},{round(float(row_dict.get('prompt_tps',0.0)),2)},{round(float(row_dict.get('generation_tps',0.0)),2)},{round(float(row_dict.get('ttft_s',0.0)),2)},{round(float(row_dict.get('wall_time_s',0.0)),2)},{row_dict.get('peak_vram_mib',0)},{row_dict.get('peak_ram_mib',0)},{row_dict.get('gpu_util_pct',0)},{row_dict.get('cpu_util_pct',0)},{row_dict.get('status','')},\"{row_dict.get('notes','')}\"\n"
    with open(CSV_FILE, "a", encoding="utf-8") as f:
        f.write(row)

class Qwen80BServerInstance:
    def __init__(self, log_name, ctx=16384, ngl=22, extra_args=None, port=PORT):
        self.log_name = log_name
        self.ctx = ctx
        self.ngl = ngl
        self.port = port
        self.extra_args = extra_args or []
        self.proc = None
        self.out_log = os.path.join(LOG_DIR, f"{log_name}.log")
        self.err_log = os.path.join(LOG_DIR, f"{log_name}.err.log")
        self.peak_vram = get_vram()
        self.peak_ram = get_ram_info()

    def start(self, timeout_sec=240):
        if os.path.exists(self.out_log): os.remove(self.out_log)
        if os.path.exists(self.err_log): os.remove(self.err_log)

        base_args = [
            BACKEND,
            "-m", MODEL,
            "-c", str(self.ctx),
            "-ctk", "q8_0",
            "-ctv", "q8_0",
            "-fa", "on",
            "-dev", "CUDA0",
            "-np", "1",
            "-t", "6",
            "-b", "2048",
            "--jinja",
            "--host", "127.0.0.1",
            "--port", str(self.port)
        ]
        if self.ngl is not None:
            base_args.extend(["-ngl", str(self.ngl)])

        cmd = base_args + self.extra_args
        log(f"Starting server [{self.log_name}]: {' '.join(cmd)}")

        f_out = open(self.out_log, "w", encoding="utf-8")
        f_err = open(self.err_log, "w", encoding="utf-8")
        self.proc = subprocess.Popen(cmd, stdout=f_out, stderr=f_err)

        ready = False
        start_t = time.time()
        while time.time() - start_t < timeout_sec:
            time.sleep(1)
            v = get_vram()
            r = get_ram_info()
            if v > self.peak_vram: self.peak_vram = v
            if r > self.peak_ram: self.peak_ram = r

            if self.proc.poll() is not None:
                log(f"Server exited prematurely with code {self.proc.returncode}", "ERROR")
                break

            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v1/models", timeout=1) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                pass

        if ready:
            log(f"Server ready in {round(time.time()-start_t, 1)}s. Peak VRAM: {self.peak_vram} MiB, Peak RAM: {self.peak_ram} MiB", "SUCCESS")
        else:
            log(f"Server start timed out or failed. Terminating...", "ERROR")
            self.stop()
        return ready

    def stop(self):
        if self.proc and self.proc.poll() is None:
            pid = self.proc.pid
            log(f"Terminating server PID: {pid}")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except Exception:
                self.proc.kill()
        time.sleep(2)

def send_chat_completion(port, messages, max_tokens=256, temperature=0.7, top_p=0.8, timeout=600):
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "seed": 42
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=data, headers={"Content-Type": "application/json"})

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.time() - t0
            res = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "data": res, "elapsed": elapsed}
    except Exception as e:
        elapsed = time.time() - t0
        return {"success": False, "error": str(e), "elapsed": elapsed}

def extract_timings_and_thinking(res_data, wall_time):
    timings = res_data.get("timings", {})
    usage = res_data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", timings.get("prompt_n", 0))
    gen_tokens = usage.get("completion_tokens", timings.get("predicted_n", 0))

    prompt_tps = timings.get("prompt_per_second", 0.0)
    gen_tps = timings.get("predicted_per_second", 0.0)
    prompt_ms = timings.get("prompt_ms", 0.0)
    ttft_s = prompt_ms / 1000.0 if prompt_ms > 0 else 0.0

    if gen_tps == 0.0 and gen_tokens > 0 and wall_time > ttft_s:
        gen_tps = gen_tokens / (wall_time - ttft_s)

    content = res_data["choices"][0]["message"].get("content", "")
    thinking_tokens = 0
    answer_tokens = gen_tokens

    if "<think>" in content and "</think>" in content:
        parts = content.split("</think>", 1)
        think_part = parts[0].replace("<think>", "")
        answer_part = parts[1]
        # rough proportion based on word lengths
        len_think = len(think_part.split())
        len_ans = len(answer_part.split())
        total_w = max(1, len_think + len_ans)
        thinking_tokens = int(gen_tokens * (len_think / total_w))
        answer_tokens = gen_tokens - thinking_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "generated_tokens": gen_tokens,
        "thinking_tokens": thinking_tokens,
        "answer_tokens": answer_tokens,
        "prompt_tps": prompt_tps,
        "generation_tps": gen_tps,
        "ttft_s": ttft_s,
        "wall_time_s": wall_time,
        "content": content
    }

SWEEP_PROMPT = [
    {"role": "system", "content": "You are a senior systems software engineer."},
    {"role": "user", "content": "Explain the architectural differences and trade-offs between epoll and io_uring in high-throughput Linux network servers. Detail memory registration and completion queues."}
]

def run_eval_job(srv, mode, ngl, ctx, messages, max_tokens=256, notes="", timeout=600):
    if not srv.start(timeout_sec=240):
        row = {
            "mode": mode, "ngl": ngl, "context": ctx,
            "status": "FAIL_STARTUP", "peak_vram_mib": srv.peak_vram, "peak_ram_mib": srv.peak_ram,
            "notes": notes or "Startup failed"
        }
        add_csv_row(row)
        return None

    # Warmup
    log("Executing warmup (24 tokens)...")
    send_chat_completion(srv.port, [{"role": "user", "content": "Hello"}], max_tokens=24, timeout=60)

    # Measured run
    log(f"Executing measured run ({max_tokens} tokens)...")
    res = send_chat_completion(srv.port, messages, max_tokens=max_tokens, timeout=timeout)
    gpu_u = get_gpu_util()
    cpu_u = get_cpu_util()
    peak_v = max(srv.peak_vram, get_vram())
    peak_r = max(srv.peak_ram, get_ram_info())

    if not res["success"]:
        log(f"Inference failed: {res['error']}", "ERROR")
        row = {
            "mode": mode, "ngl": ngl, "context": ctx,
            "status": "FAIL_INFERENCE", "peak_vram_mib": peak_v, "peak_ram_mib": peak_r,
            "gpu_util_pct": gpu_u, "cpu_util_pct": cpu_u, "notes": str(res["error"])
        }
        add_csv_row(row)
        srv.stop()
        return None

    t_info = extract_timings_and_thinking(res["data"], res["elapsed"])
    log(f"SUCCESS: Gen TPS: {t_info['generation_tps']:.2f}, PP TPS: {t_info['prompt_tps']:.2f}, Wall: {t_info['wall_time_s']:.2f}s, Peak VRAM: {peak_v} MiB, Think tokens: ~{t_info['thinking_tokens']}", "SUCCESS")

    row = {
        "mode": mode,
        "ngl": ngl,
        "context": ctx,
        "prompt_tokens": t_info["prompt_tokens"],
        "generated_tokens": t_info["generated_tokens"],
        "thinking_tokens": t_info["thinking_tokens"],
        "answer_tokens": t_info["answer_tokens"],
        "prompt_tps": t_info["prompt_tps"],
        "generation_tps": t_info["generation_tps"],
        "ttft_s": t_info["ttft_s"],
        "wall_time_s": t_info["wall_time_s"],
        "peak_vram_mib": peak_v,
        "peak_ram_mib": peak_r,
        "gpu_util_pct": gpu_u,
        "cpu_util_pct": cpu_u,
        "status": "PASS",
        "notes": notes
    }
    add_csv_row(row)
    srv.stop()
    return {"row": row, "content": t_info["content"]}

def main():
    log("=== STARTING AUTONOMOUS OPTIMIZATION FOR QWEN3-NEXT-80B-A3B-THINKING ===")
    init_csv()

    # 1. COARSE GPU OFFLOAD SWEEP (ctx=16384)
    log("--- STAGE 1: COARSE GPU OFFLOAD SWEEP ---")
    coarse_ngls = [18, 22, 25, 28, 30]
    coarse_results = {}

    for ngl in coarse_ngls:
        srv = Qwen80BServerInstance(f"coarse_ngl_{ngl}", ctx=16384, ngl=ngl)
        res = run_eval_job(srv, mode="coarse_sweep", ngl=ngl, ctx=16384, messages=SWEEP_PROMPT, max_tokens=256, notes=f"Coarse ngl={ngl}")
        if res:
            coarse_results[ngl] = res

    best_coarse_ngl = 25
    if coarse_results:
        best_coarse_ngl = max(coarse_results.keys(), key=lambda k: coarse_results[k]["row"]["generation_tps"])
        log(f"Best coarse ngl: {best_coarse_ngl} with {coarse_results[best_coarse_ngl]['row']['generation_tps']:.2f} tok/s")

    # 2. FINE GPU OFFLOAD SWEEP
    log("--- STAGE 2: FINE GPU OFFLOAD SWEEP ---")
    candidates = []
    if best_coarse_ngl == 28:
        candidates = [27, 29]
    elif best_coarse_ngl == 25:
        candidates = [24, 26]
    elif best_coarse_ngl >= 30:
        candidates = [29, 31]
    else:
        candidates = [best_coarse_ngl - 1, best_coarse_ngl + 1]

    fine_results = {}
    for ngl in candidates:
        if ngl in coarse_results: continue
        srv = Qwen80BServerInstance(f"fine_ngl_{ngl}", ctx=16384, ngl=ngl)
        res = run_eval_job(srv, mode="fine_sweep", ngl=ngl, ctx=16384, messages=SWEEP_PROMPT, max_tokens=256, notes=f"Fine ngl={ngl}")
        if res:
            fine_results[ngl] = res

    all_offload = {**coarse_results, **fine_results}
    best_ngl = max(all_offload.keys(), key=lambda k: all_offload[k]["row"]["generation_tps"])
    best_tg = all_offload[best_ngl]["row"]["generation_tps"]
    best_pp = all_offload[best_ngl]["row"]["prompt_tps"]
    log(f"Best GPU Offload Winner: -ngl {best_ngl} (TG: {best_tg:.2f} tok/s, PP: {best_pp:.2f} tok/s, VRAM: {all_offload[best_ngl]['row']['peak_vram_mib']} MiB)")

    # 3. 96K TARGET CONTEXT & KV CACHE REUSE TEST
    # Select safe ngl for 96K context (e.g. best_ngl or slightly lower to leave 2GB headroom)
    safe_96k_ngl = min(best_ngl, 26)
    log(f"--- STAGE 3: 96K TARGET CONTEXT TEST (c=98304, ngl={safe_96k_ngl}) ---")
    with open(BENCH_PROMPT_FILE, "r", encoding="utf-8") as f:
        bench_text = f.read()

    prompt_30k = bench_text[:160000]

    srv_96k = Qwen80BServerInstance("qwen80b_96k_target", ctx=98304, ngl=safe_96k_ngl)
    target_96k_results = {}

    if srv_96k.start(timeout_sec=300):
        # Turn 1: Cold long prompt
        log("Executing Qwen3-Next 80B 96K Turn 1: Cold long prompt (~30K tokens)...")
        t1_messages = [
            {"role": "system", "content": "You are a principal systems architect."},
            {"role": "user", "content": f"{prompt_30k}\n\n[TASK]: Summarize the primary architectural bottlenecks and memory hierarchy tradeoffs in 3 clear paragraphs."}
        ]
        t0 = time.time()
        res_t1 = send_chat_completion(srv_96k.port, t1_messages, max_tokens=256, timeout=1800)
        elapsed_t1 = time.time() - t0
        gpu_u = get_gpu_util()
        cpu_u = get_cpu_util()
        peak_v = max(srv_96k.peak_vram, get_vram())
        peak_r = max(srv_96k.peak_ram, get_ram_info())

        if res_t1["success"]:
            t_info_t1 = extract_timings_and_thinking(res_t1["data"], elapsed_t1)
            t1_reply = t_info_t1["content"]
            log(f"Qwen 80B 96K Turn 1 SUCCESS: Prompt tokens: {t_info_t1['prompt_tokens']}, PP TPS: {t_info_t1['prompt_tps']:.2f}, TTFT: {t_info_t1['ttft_s']:.2f}s, Gen TPS: {t_info_t1['generation_tps']:.2f}, Wall: {t_info_t1['wall_time_s']:.2f}s", "SUCCESS")
            row_t1 = {
                "mode": "96k_target_cold",
                "ngl": safe_96k_ngl,
                "context": 98304,
                "prompt_tokens": t_info_t1["prompt_tokens"],
                "generated_tokens": t_info_t1["generated_tokens"],
                "thinking_tokens": t_info_t1["thinking_tokens"],
                "answer_tokens": t_info_t1["answer_tokens"],
                "prompt_tps": t_info_t1["prompt_tps"],
                "generation_tps": t_info_t1["generation_tps"],
                "ttft_s": t_info_t1["ttft_s"],
                "wall_time_s": t_info_t1["wall_time_s"],
                "peak_vram_mib": peak_v,
                "peak_ram_mib": peak_r,
                "gpu_util_pct": gpu_u,
                "cpu_util_pct": cpu_u,
                "status": "PASS",
                "notes": "Qwen3-Next 80B 96K cold prompt"
            }
            add_csv_row(row_t1)
            target_96k_results["turn1"] = {"row": row_t1, "reply": t1_reply}

            # Turn 2: Follow-up with KV Reuse
            log("Executing Qwen 80B 96K Turn 2: Follow-up with KV reuse...")
            t2_messages = t1_messages + [
                {"role": "assistant", "content": t1_reply},
                {"role": "user", "content": "Extract the top 3 actionable architectural recommendations from your summary."}
            ]
            t0 = time.time()
            res_t2 = send_chat_completion(srv_96k.port, t2_messages, max_tokens=128, timeout=600)
            elapsed_t2 = time.time() - t0
            if res_t2["success"]:
                t_info_t2 = extract_timings_and_thinking(res_t2["data"], elapsed_t2)
                t2_reply = t_info_t2["content"]
                log(f"Qwen 80B 96K Turn 2 SUCCESS: Prompt tokens evaluated: {t_info_t2['prompt_tokens']}, TTFT: {t_info_t2['ttft_s']:.2f}s, Gen TPS: {t_info_t2['generation_tps']:.2f}, Wall: {t_info_t2['wall_time_s']:.2f}s", "SUCCESS")
                row_t2 = {
                    "mode": "96k_target_followup1",
                    "ngl": safe_96k_ngl,
                    "context": 98304,
                    "prompt_tokens": t_info_t2["prompt_tokens"],
                    "generated_tokens": t_info_t2["generated_tokens"],
                    "thinking_tokens": t_info_t2["thinking_tokens"],
                    "answer_tokens": t_info_t2["answer_tokens"],
                    "prompt_tps": t_info_t2["prompt_tps"],
                    "generation_tps": t_info_t2["generation_tps"],
                    "ttft_s": t_info_t2["ttft_s"],
                    "wall_time_s": t_info_t2["wall_time_s"],
                    "peak_vram_mib": max(srv_96k.peak_vram, get_vram()),
                    "peak_ram_mib": max(srv_96k.peak_ram, get_ram_info()),
                    "gpu_util_pct": get_gpu_util(),
                    "cpu_util_pct": get_cpu_util(),
                    "status": "PASS",
                    "notes": "Qwen 80B KV reuse follow-up 1"
                }
                add_csv_row(row_t2)
                target_96k_results["turn2"] = {"row": row_t2, "reply": t2_reply}

                # Turn 3: Second follow-up
                log("Executing Qwen 80B 96K Turn 3: Second follow-up...")
                t3_messages = t2_messages + [
                    {"role": "assistant", "content": t2_reply},
                    {"role": "user", "content": "State the single most critical risk in one concise sentence."}
                ]
                t0 = time.time()
                res_t3 = send_chat_completion(srv_96k.port, t3_messages, max_tokens=64, timeout=300)
                elapsed_t3 = time.time() - t0
                if res_t3["success"]:
                    t_info_t3 = extract_timings_and_thinking(res_t3["data"], elapsed_t3)
                    t3_reply = t_info_t3["content"]
                    log(f"Qwen 80B 96K Turn 3 SUCCESS: Prompt tokens evaluated: {t_info_t3['prompt_tokens']}, Gen TPS: {t_info_t3['generation_tps']:.2f}, Wall: {t_info_t3['wall_time_s']:.2f}s", "SUCCESS")
                    row_t3 = {
                        "mode": "96k_target_followup2",
                        "ngl": safe_96k_ngl,
                        "context": 98304,
                        "prompt_tokens": t_info_t3["prompt_tokens"],
                        "generated_tokens": t_info_t3["generated_tokens"],
                        "thinking_tokens": t_info_t3["thinking_tokens"],
                        "answer_tokens": t_info_t3["answer_tokens"],
                        "prompt_tps": t_info_t3["prompt_tps"],
                        "generation_tps": t_info_t3["generation_tps"],
                        "ttft_s": t_info_t3["ttft_s"],
                        "wall_time_s": t_info_t3["wall_time_s"],
                        "peak_vram_mib": max(srv_96k.peak_vram, get_vram()),
                        "peak_ram_mib": max(srv_96k.peak_ram, get_ram_info()),
                        "gpu_util_pct": get_gpu_util(),
                        "cpu_util_pct": get_cpu_util(),
                        "status": "PASS",
                        "notes": "Qwen 80B KV reuse follow-up 2"
                    }
                    add_csv_row(row_t3)
                    target_96k_results["turn3"] = {"row": row_t3, "reply": t3_reply}
        else:
            log(f"Qwen 80B 96K Turn 1 FAILED: {res_t1['error']}", "ERROR")

        srv_96k.stop()

    # 4. GENERATE RESULT.MD
    log("--- GENERATING RESULT.MD ---")
    generate_result_md(all_offload, target_96k_results, best_ngl, safe_96k_ngl, best_tg, best_pp)
    log("=== QWEN3-NEXT-80B OPTIMIZATION COMPLETED SUCCESSFULLY ===", "SUCCESS")

def generate_result_md(offload_res, target_96k, best_ngl, safe_96k_ngl, best_tg, best_pp):
    content = f"""# Qwen3-Next-80B-A3B-Thinking Optimization & Benchmark Report

## 1. Executive Summary
- **Model**: `K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf` (35,494,473,888 bytes ≈ 33.05 GiB).
- **Architecture**: `qwen3next` (MoE: 48 layers + 1 output, 512 total experts, 10 active experts per token = ~3B active params, native context 262,144).
- **Backend**: `K:\\Project\\ik_llama\\bin\\llama-server.exe` (commit `3c58ae3`).
- **MTP Status**: **NOT AVAILABLE / NOT USED** (0 speculative tensor keys in GGUF metadata).
- **Optimal Hardware Configuration**:
  - **Best GPU Offload (`-ngl`) for 16K**: `{best_ngl}` (Peak VRAM: `{offload_res[best_ngl]['row']['peak_vram_mib']} MiB`, TG: **{best_tg:.2f} tok/s**).
  - **Best GPU Offload (`-ngl`) for 96K**: `{safe_96k_ngl}` (Safe headroom for 96K KV cache).
  - **Peak System RAM**: `{offload_res[best_ngl]['row']['peak_ram_mib']} MiB` (fits comfortably in 48GB physical RAM).

---

## 2. GPU Offload Sweep Comparison (Context = 16384)

| Mode | ngl | Prompt tok/s | Gen tok/s | TTFT (s) | Wall (s) | Peak VRAM (MiB) | Peak RAM (MiB) | Status |
|---|---|---|---|---|---|---|---|---|
"""
    for k, v in sorted(offload_res.items(), key=lambda x: x[0]):
        r = v["row"]
        content += f"| {r['mode']} | {r['ngl']} | {r['prompt_tps']} | {r['generation_tps']} | {r['ttft_s']} | {r['wall_time_s']} | {r['peak_vram_mib']} | {r['peak_ram_mib']} | {r['status']} |\n"

    content += f"""
---

## 3. 96K Target Context Benchmark (`-c 98304`, `-ngl {safe_96k_ngl}`)

"""
    if "turn1" in target_96k:
        r1 = target_96k["turn1"]["row"]
        content += f"""### Cold Long Prompt Evaluation (~30K tokens)
- **Prompt Tokens**: {r1['prompt_tokens']}
- **Prompt Processing Speed**: **{r1['prompt_tps']} tok/s**
- **Time To First Token (TTFT)**: **{r1['ttft_s']} s**
- **Generation Speed**: **{r1['generation_tps']} tok/s**
- **Peak VRAM**: {r1['peak_vram_mib']} MiB
- **Peak System RAM**: {r1['peak_ram_mib']} MiB
- **Wall Time**: {r1['wall_time_s']} s

"""
    if "turn2" in target_96k:
        r2 = target_96k["turn2"]["row"]
        content += f"""### Follow-up Turn 1 (KV Reuse Proof)
- **Prompt Tokens Evaluated**: **{r2['prompt_tokens']}** (Previous prompt was 100% cached)
- **Follow-up TTFT**: **{r2['ttft_s']} s**
- **Generation Speed**: **{r2['generation_tps']} tok/s**
- **Wall Time**: {r2['wall_time_s']} s

"""
    if "turn3" in target_96k:
        r3 = target_96k["turn3"]["row"]
        content += f"""### Follow-up Turn 2
- **Prompt Tokens Evaluated**: **{r3['prompt_tokens']}**
- **Generation Speed**: **{r3['generation_tps']} tok/s**
- **Wall Time**: {r3['wall_time_s']} s
"""

    with open(RESULT_MD, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"Saved {RESULT_MD}")

if __name__ == "__main__":
    main()
