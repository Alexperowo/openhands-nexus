# Official llama.cpp Backend Analysis (Release b10816)

## 1. Backend Provenance & Environment
- **Repository**: `https://github.com/ggml-org/llama.cpp`
- **Release Tag**: `b10816`
- **Commit**: `427291b5b34cd914a31b3fd3b61a68f6184f4b9f`
- **Binary Package**: `llama-b10816-bin-win-cuda-12.4-x64.zip` (SHA256: `f567f273ef0cad7aa1835c94426aa38577df16ddd1d32f5085e1a503ae106697`)
- **CUDA Runtime**: `cudart-llama-bin-win-cuda-12.4-x64.zip` (SHA256: `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`)
- **Build**: Windows x86_64, CUDA 12.4, Clang 20.1.8
- **Executable**: `K:\Project\LLM-tests\Qwen3-Next-Mainline\backend\llama-server.exe`
- **Version String**: `version: 0.4.0-dev (build 10816, commit 427291b5b)`

---

## 2. Architectural Comparison: Official `llama.cpp b10816` vs `ik_llama 3c58ae3`

| Feature | `ik_llama 3c58ae3` | Official `llama.cpp b10816` | Impact on Qwen3-Next-80B |
| :--- | :--- | :--- | :--- |
| **`qwen3next` Architecture Support** | Partially implemented (basic transformer only) | Fully supported in core GGML/llama graph builders | Main model loads in ~11-30s without warnings |
| **External MTP Companion (`MTP-ONLY-*.gguf`)** | **BROKEN** (`check_tensor_dims: blk.0.attn_norm.weight not found`) | **FULLY OPERATIONAL** via `--spec-type draft-mtp -md <file>` | Loads block 48 predictor head cleanly, drafts and accepts tokens |
| **Speculative Syntax** | `--spec-type mtp:n_max=1` | `--spec-type draft-mtp --spec-draft-n-max 1 -md <file>` | Clean standardized CLI syntax |
| **Reasoning Loop Control** | Forced `</think>` caused endless reasoning in `content` | Native `--reasoning-budget-message` injects prompt before `</think>` | **ELIMINATES REASONING LOOP**; model cleanly transitions to final answer and ends with `stop` |
| **Per-Request Thinking Budget** | `"thinking_budget_tokens": <N>` | `"thinking_budget_tokens": <N>` supported out-of-the-box | Dynamic per-request control without restarting |
| **CUDA Device Selection** | `-dev CUDA0` | `-dev CUDA0` (auto-detects NVIDIA GeForce RTX 2080 Ti 22GB) | Identical GPU memory mapping |
| **KV Cache Datatypes** | Requires `-ctk q8_0 -ctv q8_0` for CPU offload | Supports `-ctk q8_0 -ctv q8_0` with Flash Attention | Stable memory footprint |

---

## 3. Verified Native Flags in `b10816`
- `--reasoning-format [none|deepseek|deepseek-legacy]` (default: `auto`)
- `-rea, --reasoning [on|off|auto]`
- `--reasoning-budget <N>` (`-1` for unrestricted, `0` for immediate end, `N > 0` for budget)
- `--reasoning-budget-message <MESSAGE>`: Injected before `</think>` when budget expires. Proved effective at stopping internal monologue loops.
- `--reasoning-effort [minimal|low|medium|high|xhigh|max]`
- `--spec-type [none|draft-simple|draft-eagle3|draft-mtp|draft-dflash|...]`
- `--spec-draft-model, -md <FILE>`
- `--spec-draft-n-max <N>` (default: 3)
- `--spec-draft-p-min <P>` (default: 0.00)
