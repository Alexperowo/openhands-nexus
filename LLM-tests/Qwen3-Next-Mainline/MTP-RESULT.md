# Qwen3-Next-80B MTP Benchmark Report (Official llama.cpp b10816)

## 1. MTP Verification Summary
Unlike `ik_llama commit 3c58ae3` (which failed to load standalone MTP companion files), the official `ggml-org/llama.cpp b10816` **fully and natively supports** the standalone MTP companion file for `qwen3next` via:
`--spec-type draft-mtp --spec-draft-n-max <N> -md <MTP_GGUF>`

## 2. Benchmark Comparison (ngl=26, context=16384)

| Configuration | Speculative Depth (`n_max`) | Generation Speed (TG tok/s) | Accepted Draft Tokens | Wall Time (s) | Peak VRAM (MiB) | Gain vs Baseline (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **MTP OFF Baseline** | N/A | 15.64 tok/s | 0 | 66.91s | 19,124 MiB | Baseline (0.0%) |
| **MTP Q4** | **n_max=1** | **17.79 tok/s** | **415** | **58.90s** | **20,482 MiB** | **+13.7% (WINNER)** |
| **MTP Q4** | n_max=2 | 17.01 tok/s | 511 | 61.49s | 20,482 MiB | +8.8% |
| **MTP Q4** | n_max=3 | 16.03 tok/s | 534 | 65.23s | 20,482 MiB | +2.5% |
| **MTP Q6** | n_max=1 | 17.20 tok/s | 396 | 60.82s | 20,744 MiB | +10.0% |
| **MTP Q6** | n_max=2 | 16.45 tok/s | 487 | 63.62s | 20,754 MiB | +5.2% |
| **MTP Q6** | n_max=3 | 15.98 tok/s | 538 | 65.44s | 20,754 MiB | +2.2% |

## 3. Findings & Winner
- **MTP Winner**: **`MTP_Q4` at `n_max=1`**
- **Wall Time Reduction**: Latency dropped from 66.91s to 58.90s (-12.0% total turn duration).
- **VRAM Impact**: MTP adds ~1,358 MiB VRAM for draft context and layer 48 weights, safely fitting within RTX 2080 Ti (20,482 MiB used out of 22,527 MiB).
- **Q4 vs Q6**: Q4 is strictly superior to Q6: it delivers higher throughput (17.79 vs 17.20 tok/s) and consumes ~260 MiB less VRAM.
- **Speculative Depth Tradeoff**: `n_max=1` is optimal. Increasing `n_max` to 2 or 3 drafts more tokens (up to 534 accepted), but the verification overhead on hybrid CPU/GPU inference reduces net generation throughput.
