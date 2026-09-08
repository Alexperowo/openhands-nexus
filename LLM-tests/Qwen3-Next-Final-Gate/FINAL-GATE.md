# FINAL GATE REPORT: Qwen3-Next-80B-A3B-Thinking

## 1. Executive Summary & Final Verdict

- **Model Evaluated**: `Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf` (33.05 GiB)
- **Hardware Platform**: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM) + 48 GB System RAM
- **Backend Binary**: `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`)
- **Benchmark Baseline**: `Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf` (Production config)

### Core Verdicts:
- **`BEST_NEXT_CONFIG`**:
  ```cmd
  llama-server.exe -m "K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf" ^
    -ngl 26 -c 16384 -fa on -ctk q8_0 -ctv q8_0 -dev CUDA0 -np 1 -t 6 ^
    --jinja --reasoning on --reasoning-format deepseek-legacy --host 127.0.0.1 --port 8080
  ```
- **`MTP_RECOMMENDED`**: **`OFF`**
- **`NEXT_DEFAULT_REASONING`**: `thinking_budget_tokens: 2048`, `max_tokens: 5120`
- **`NEXT_DEEP_REASONING`**: `thinking_budget_tokens: 4096`, `max_tokens: 8192`
- **`NEXT_BEATS_QWEN27_MATERIALLY`**: **`NO`**
- **`RECOMMEND_NEXT_AS_HEAVY`**: **`NO`**
- **`READY_FOR_OPENHANDS_INTEGRATION`**: **`NO`**
- **`UNRESOLVED`**:
  1. `ik_llama` commit `3c58ae3` lacks MTP graph and loader support for `qwen3next` (cannot load standalone predictor companions).
  2. Qwen3-Next exhibits extreme thinking loops (often exceeding 4000-8000 tokens per prompt), causing truncated answers (`finish_reason: length`) and unacceptably high turn latency (4 to 9 minutes per tool turn).

---

## 2. MTP Investigation & Benchmark Analysis

### Inventory:
- **Main Model**: `Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf` (33.05 GiB, 48 layers, architecture `qwen3next`)
- **MTP Q4**: `Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf` (1.40 GiB, 23 tensors for block 48)
- **MTP Q6**: `Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q6_K.gguf` (1.74 GiB, 23 tensors for block 48)

### Runtime Probe Results:
- **MTP Q4**: `FAILED` with exit code 1 (`llama_model_load: check_tensor_dims: tensor 'blk.0.attn_norm.weight' not found`).
- **MTP Q6**: `FAILED` with exit code 1 (`llama_model_load: check_tensor_dims: tensor 'blk.0.attn_norm.weight' not found`).
- **Technical Root Cause**:
  1. In `src/graphs/build_qwen3next.cpp`, there is **no MTP computation graph** implemented.
  2. In `src/llama-model.cpp`, the tensor map for `LLM_ARCH_QWEN3NEXT` lacks `nextn` tensors (`eh_proj`, `enorm`, `hnorm`, `shared_head_norm`).
  3. In `src/common/speculative.cpp`, `common_speculative_target_has_appended_mtp_contract()` only includes `step35`, `deepseek4`, and `qwen35_family`. It routes `qwen3next` companions to `common_speculative_load_draft_model()`, which requires a full model file starting from layer 0.

### Baseline (MTP OFF) Performance:
- **Best GPU Offload**: `ngl 26` (VRAM: 19.15 GB / 22.0 GB, leaving 2.85 GB headroom).
- **Generation Speed**: **16.5 - 17.5 tok/s** at 16K context; **12.5 - 13.3 tok/s** at 96K context.
- **Prompt Processing**: **69.3 tok/s** at 16K context; **190.3 tok/s** at 96K context (cold).
- **KV Cache Reuse**: Cold TTFT = 158.3s -> Follow-up TTFT = 1.28s (KV cache fully preserved).
- **MTP Gain**: **0.0%** (MTP not operable).

---

## 3. Reasoning & Thinking Control Investigation

### Backend Mechanism in `ik_llama` (commit `3c58ae3`):
- **Supported Per-Request Parameter**: `"thinking_budget_tokens": <N>` in `/v1/chat/completions` request body.
- **Dynamic Switching**: **YES**, can be changed per request without server restart.
- **Format Options**: `--reasoning-format deepseek` (separates into `reasoning_content`) or `deepseek-legacy` (keeps `<think>` in `content` while populating `reasoning_content`).

### Live Testing of Reasoning Budgets:
| Profile | Budget | Max Tokens | Generated Tokens | Finish Reason | Turn Latency | Output State |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **NEXT-LOW** | 1024 | 3072 | 3072 | `length` | 191.7s (3.2m) | **TRUNCATED** (Continued thought in content) |
| **NEXT-MEDIUM** | 2048 | 5120 | 5120 | `length` | 321.4s (5.4m) | **TRUNCATED** (Continued thought in content) |
| **NEXT-HIGH** | 4096 | 8192 | 8192 | `length` | 520.5s (8.7m) | **TRUNCATED** (Endless thinking loop) |

**Key Flaw Observed**: When `thinking_budget_tokens` forcibly injects `</think>`, Qwen3-Next does not realize it must summarize; it continues its internal monologue directly into the `content` field until hitting `max_tokens`. Without a hard limit of at least 8K-16K tokens, it rarely completes non-trivial tasks.

---

## 4. Head-to-Head Quality Gate: Qwen3-Next-80B vs Qwen3.8-27B-Opus

Both models were evaluated on three identical, ground-truth-anchored engineering benchmarks (temperature 0.6, max_tokens 4096).

| Benchmark | Qwen3.8-27B-Opus (Production MTP) | Qwen3-Next-80B-A3B (ngl 26) | Winner |
| :--- | :---: | :---: | :---: |
| **Test A: Code Audit** (8 Seeded Defects) | **8 / 8 BUGS FOUND** (100% Score)<br>Latency: **77.8s** (finish: `stop`) | **0 / 8 DELIVERED** (Exhausted in thinking)<br>Latency: **262.7s** (finish: `length`) | **Qwen27** |
| **Test B: Debugging** (Contradiction Detection) | **CONTRADICTION DETECTED**<br>Refuted false heap claim, found cgroup OOM<br>Latency: **125.4s** (finish: `stop`) | **TRUNCATED** (389 characters)<br>Spotted contradiction but cut off mid-sentence<br>Latency: **260.3s** (finish: `length`) | **Qwen27** |
| **Test C: Architecture** (12 Ledger Requirements) | **TRUNCATED IN THINKING**<br>Exhausted 4096 tokens in design<br>Latency: **128.4s** (finish: `length`) | **TRUNCATED IN THINKING**<br>Exhausted 4096 tokens in design<br>Latency: **255.7s** (finish: `length`) | **TIE** |

### Head-to-Head Comparison Summary:
- **Bugs found only by Next**: 0.
- **Bugs found only by Qwen27**: All 8 bugs in Test A.
- **Contradiction Detection**: Qwen27 cleanly dismantled the false premise, proved heap usage was low (412 MiB), identified container cgroup exhaustion, and delivered a complete incident report. Next80 saw the contradiction in thought, but could not produce a finished response.
- **Latency Disparity**: Qwen27 generates at **33 - 40 tok/s**, answering complex queries in **1 - 2 minutes**. Qwen3-Next generates at **16 tok/s**, taking **4.5 minutes** to produce an incomplete truncated turn.

---

## 5. Architectural Role & Next Steps

1. **Production Role**:
   - `Qwen3-Next-80B-A3B-Thinking` should **NOT** replace or augment `Qwen3.8-27B-Opus` as a heavy reasoning model in OpenHands today.
   - Its unconstrained verbosity, inability to cleanly respect token budgets, and 16 tok/s generation make it an agent blocker (frequent timeouts, truncated tool calls, and high token costs).
2. **Current OpenHands Configuration**:
   - Keep `Qwen3.8-27B-Opus` + `Ornith-1.5-35B` as the primary operational models in `llama-swap`.
   - Production files (`config.yaml`, profiles, `BEST-*.cmd`) remain untouched and safe.
