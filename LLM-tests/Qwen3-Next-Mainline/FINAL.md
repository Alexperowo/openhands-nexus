# Qwen3-Next Rescue & Multi-Model Mainline Compatibility Final Report

## Executive Summary

This investigation tested official **`ggml-org/llama.cpp` (release `b10816`, commit `427291b5b`)** to determine:
1. Whether official `llama.cpp` fixes the two blocking defects that caused **Qwen3-Next-80B-A3B-Thinking** to fail its initial production gate under `ik_llama commit 3c58ae3`:
   - **Absence of companion MTP support** (`MTP-ONLY-*.gguf` loading crash).
   - **Uncontrollable reasoning loop** when token budgets are exhausted (`finish_reason: length` instead of concluding).
2. Whether our two active production models (**Qwen3.8-27B-Opus** and **Ornith-1.5-35B**) are compatible with this official build, enabling a unified, maintained backend.

### Core Verdict
- **Qwen3-Next-80B IS RESCUED AND 100% OPERATIONAL on official `llama.cpp b10816`**:
  - **MTP**: Works natively with external companion `--spec-type draft-mtp -md "Qwen3-Next-80B-...-MTP-ONLY-Q4_K_M.gguf"`, yielding **+13.7% speedup** (17.79 tok/s vs 15.64 tok/s).
  - **Reasoning Loop**: Fully solved via native `--reasoning-budget-message "Conclude reasoning immediately and output the final answer now."`. In both `NEXT-NORMAL` and `NEXT-DEEP`, generation terminates cleanly with **`finish_reason: stop`** and provides well-formed final answers.
  - **Quality Gate**: Passed with flying colors (100% defect detection [8/8 bugs found] in Code Audit, detected forensic contradiction and false heap claim in Forensic Debugging).
  - **96K Long-Context**: Blazing fast cold prompt processing (**404.1 tok/s**) and instant KV-cache reuse (**1.28s - 2.17s TTFT**).
- **Multi-Model Production Compatibility**:
  - **Qwen3.8-27B-Opus**: 100% functional parity. Embedded MTP (`n_max=3`) achieves 23.91 tok/s, OpenAI tool calling works out-of-the-box (`--jinja`), and 96K KV reuse is instant (1.51s TTFT).
  - **Ornith-1.5-35B**: Functional parity across Vision (`mmproj` works cleanly), OpenAI tool calling, dynamic thinking toggling (0 vs 128 tokens), and 96K KV reuse. Raw generation reaches **74.0 tok/s**. Cold prompt processing on 96K is ~42 tok/s (slower than `ik_llama`'s specialized unmerged MoE batch kernels), but once cached, follow-up queries respond with ~6.9s TTFT and full draft acceptance.

---

## 1. Multi-Model Compatibility Matrix

| Metric / Capability | Qwen3-Next-80B-A3B-Thinking | Qwen3.8-27B-Opus-Distill-v2 | Ornith-1.5-35B-MTP-19G-ICE |
| :--- | :---: | :---: | :---: |
| **Model Quant & Size** | UD-Q3_K_XL (38.8 GB) | Q4_K_M (16.2 GB) | MTP-19G-ICE (19.4 GB) |
| **Official b10816 Status** | **PASS (Fully Rescued)** | **PASS (Drop-in Ready)** | **PASS (Production Ready)** |
| **Speculative Decoding** | External Companion `MTP_Q4` | Embedded MTP (`n_max=3`) | Embedded MTP (`n_max=1`) |
| **TG Speed (16K)** | **17.79 tok/s** (+13.7%) | **23.91 tok/s** (+7.6%) | **74.01 tok/s** (MTP OFF) / 54.72 (MTP ON) |
| **TG Speed (96K Context)** | **12.75 tok/s** | **9.61 tok/s** | **12.26 tok/s** |
| **Cold PP Speed (96K)** | **404.1 tok/s** | **47.9 tok/s** | **41.7 tok/s** |
| **KV Cache Reuse (TTFT)** | **1.28s - 2.17s** | **1.51s** | **6.98s** |
| **Thinking Budget Control** | **PASS** (Zero runaway loops) | **PASS** (Pure content direct mode) | **PASS** (Dynamic budget 0 vs 128) |
| **OpenAI Tool Calling** | N/A (Heavy Reasoning) | **PASS** (`lookup_stock_price`) | **PASS** (`lookup_stock_price`) |
| **Multimodal / Vision** | N/A | N/A | **PASS** (`mmproj-BF16`, 19.3 GB VRAM) |
| **Peak VRAM (96K Mode)** | **21,458 MiB** | **20,258 MiB** | **19,794 MiB** |
| **Free VRAM Headroom** | **2,574 MiB** | **3,774 MiB** | **4,238 MiB** |

---

## 2. Detailed Findings for Qwen3-Next-80B-A3B

### A. MTP Companion Breakthrough
In `ik_llama commit 3c58ae3`, passing `-md` caused an immediate assertion crash (`speculative draft model unsupported`).
In official `llama.cpp b10816`:
- Loading `Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf` as companion via `--spec-type draft-mtp --spec-draft-n-max 1` works flawlessly.
- Load time is only 11.8s.
- TG speed increases from **15.64 tok/s to 17.79 tok/s (+13.7%)**.
- `MTP_Q4` outperforms `MTP_Q6` (17.79 vs 17.20 tok/s) and uses 260 MiB less VRAM.

### B. Reasoning Budget & Loop Control
In `ik_llama`, when `thinking_budget_tokens` expired, the model repeatedly outputted ellipses, empty thoughts, or repeated itself until hitting `max_tokens` (`finish_reason: length`), never writing the final answer.
In `b10816`, passing:
`--reasoning-budget-message "Conclude reasoning immediately and output the final answer now."`
causes the server to inject a graceful conclusion trigger into the thinking sequence when the budget is reached.
- **`NEXT-NORMAL`** (Budget 1024, Max 4096): Latency 131.4s, 972 draft tokens accepted, terminates cleanly with **`finish_reason: stop`**.
- **`NEXT-DEEP`** (Budget 2048, Max 6144): Latency 175.0s, 1273 draft tokens accepted, terminates cleanly with **`finish_reason: stop`**.

### C. Quality Verification Under Rescued Runtime
Tested against the identical ground-truth prompts from the heavy model comparison:
- **Test A (Concurrency Bug Audit in Go Distributed Broker)**:
  - Discovered all **8 / 8 vulnerabilities (100%)**, including subtle double-read race condition and channel leak.
  - Provided clean, idiomatic Go patch.
  - Finished with `finish_reason: stop` (1,725 MTP draft tokens accepted).
- **Test B (Forensic Memory Leak in Kubernetes Netty Gateway)**:
  - Thoroughly debunked the prompt's false premise (proved JVM heap was healthy at 412 MB / 40%).
  - Correctly diagnosed cgroup memory throttling and Netty native off-heap buffer leaks.
  - Finished with `finish_reason: stop` (1,312 MTP draft tokens accepted).

---

## 3. Production Readiness & Recommendation

### Can Official llama.cpp Serve as a Unified Production Backend?
**YES, with clear architectural alignment:**

1. **For Qwen3-Next-80B-A3B-Thinking (Heavy Tier / Architect Role)**:
   - Official `llama.cpp b10816` is **the only viable runtime** because `ik_llama` crashes on its companion MTP and suffers runaway reasoning loops.
   - On `b10816`, Next is exceptionally capable: 17.8 tok/s generation, 404 tok/s cold prompt ingestion, zero memory overflows, and flawless reasoning termination.
2. **For Qwen3.8-27B-Opus (Primary Executive / Coding Tier)**:
   - Official `llama.cpp b10816` is a 100% equivalent drop-in replacement. Embedded MTP, tool calling, and 96K KV reuse are completely validated.
3. **For Ornith-1.5-35B (Vision / Fast Executive Tier)**:
   - Official `llama.cpp b10816` supports all functional modalities (Vision via mmproj, tool calling, dynamic thinking, embedded MTP).
   - If extremely long cold prompt processing speed (>50K tokens cold in a single turn) is paramount, `ik_llama` retains specialized MoE batching kernels (~800 tok/s vs ~42 tok/s). However, in interactive multi-turn sessions (where KV cache is reused), official `b10816` delivers responses in seconds with 74 tok/s raw output.

### Recommended Launch Command for Qwen3-Next-80B:
```cmd
K:\Project\LLM-tests\Qwen3-Next-Mainline\backend\llama-server.exe ^
  -m "K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf" ^
  -md "K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf" ^
  -c 98304 ^
  -ngl 26 ^
  -fa on ^
  -ctk q8_0 ^
  -ctv q8_0 ^
  -np 1 ^
  -t 6 ^
  -dev CUDA0 ^
  --spec-type draft-mtp ^
  --spec-draft-n-max 1 ^
  --reasoning-format deepseek ^
  --reasoning-budget-message "Conclude reasoning immediately and output the final answer now." ^
  --host 127.0.0.1 ^
  --port 8080
```
