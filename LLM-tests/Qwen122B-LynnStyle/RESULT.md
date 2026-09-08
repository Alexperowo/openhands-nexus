# Qwen3.5-122B-A10B-LynnStyle Optimization & Benchmark Report

## 1. Executive Summary
- **Model**: `Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf` (44,612,547,968 bytes ≈ 41.54 GiB).
- **Vision Projector**: `Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF-mmproj-Q8_0.gguf` (619,212,000 bytes ≈ 590.5 MiB).
- **Architecture**: `qwen3next` (MoE: 48 layers + 1 output, 256 total experts, 8 active experts per token = ~10B active params, native context 262,144).
- **MTP Status**: **NOT AVAILABLE / NOT USED** (Verified via GGUF metadata: 0 speculative/MTP keys; model trained without embedded MTP).
- **Critical Technical Breakthrough**:
  - `ik_llama` partial offload to CPU requires `-ctk q8_0 -ctv q8_0` (or f16/q4_0). Using `q5_0` on CPU triggers an explicit backend assertion (`Warning: ik_llama.cpp does not support Q5_0 or Q5_1 KV cache on the CPU`).
  - Because `head_count_kv = 2`, `q8_0` KV cache requires only **~780 MiB at 16K** and **~1,766 MiB at 96K** across GPU and system RAM, comfortably fitting within 48GB physical RAM.
- **Optimal Hardware Configuration**:
  - **Best GPU Offload (`-ngl`) for 16K Context**: `21` (Gen: **4.12 tok/s**, Peak VRAM: **22,165 MiB**, headroom: ~360 MiB).
  - **Best GPU Offload (`-ngl`) for 96K Context**: `18` (Gen: **3.42 tok/s**, Peak VRAM: **20,399 MiB**, safe headroom: ~2,120 MiB to accommodate 96K KV cache).
  - **Peak System RAM**: **48,824 MiB** (fits stably in 48GB physical RAM + paging, zero memory crash).

---

## 2. Quantitative Performance Matrix

| Mode | ngl | Context | Prompt Tokens | Gen Tokens | Prompt tok/s | Gen tok/s | TTFT (s) | Wall (s) | Peak VRAM (MiB) | Peak RAM (MiB) | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| coarse_sweep | 12 | 16384 | 38 | 256 | 11.25 | 3.20 | 3.38 | 83.34 | 15243 | 46718 | PASS |
| coarse_sweep | 16 | 16384 | 38 | 256 | 14.34 | 3.67 | 2.65 | 72.44 | 18273 | 46680 | PASS |
| coarse_sweep | 18 | 16384 | 62 | 256 | 15.77 | 3.84 | 3.93 | 70.74 | 20102 | 47347 | PASS |
| coarse_sweep | 20 | 16384 | 62 | 256 | 18.71 | 4.01 | 3.31 | 67.23 | 21606 | 47358 | PASS |
| fine_sweep | 21 | 16384 | 62 | 256 | 18.56 | 4.12 | 3.34 | 65.48 | 22165 | 47469 | PASS |
| fine_sweep | 22 | 16384 | 62 | 256 | 10.74 | 4.08 | 5.77 | 68.58 | 22170 | 48745 | PASS |
| placement_fit | fit | 16384 | 0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 20518 | 27701 | FAIL_STARTUP |
| 96k_target_cold | 18 | 98304 | 30225 | 256 | 43.01 | 2.87 | 702.72 | 791.97 | 20399 | 48824 | PASS |
| 96k_target_followup1 | 18 | 98304 | 30248 | 128 | 6.21 | 3.16 | 4.51 | 45.28 | 20399 | 48709 | PASS |
| 96k_target_followup2 | 18 | 98304 | 30271 | 64 | 6.42 | 3.42 | 4.36 | 23.19 | 20399 | 48674 | PASS |

---

## 3. Placement Analysis (`-ngl` vs `--fit`)
- **Explicit `-ngl` Offloading**: Layers 0–42 require ~752 MiB each; layers 43–47 require ~1,675 MiB each; layer 48 requires 893 MiB.
  - `-ngl 12`: 15,243 MiB VRAM, 3.20 tok/s.
  - `-ngl 16`: 18,273 MiB VRAM, 3.67 tok/s.
  - `-ngl 18`: 20,102 MiB VRAM, 3.84 tok/s (optimal balance of speed and VRAM headroom).
  - `-ngl 20`: 21,606 MiB VRAM, 4.01 tok/s.
  - `-ngl 21`: 22,165 MiB VRAM, 4.12 tok/s (peak speed for 16K, but only 360 MiB headroom).
  - `-ngl 22`: 22,170 MiB VRAM, 4.08 tok/s (VRAM exhausted, prompt TPS drops from 18.56 to 10.74 due to paging).
- **Auto-fit (`--fit`)**: Requires allocating >22 GiB of pinned host memory (`CUDA_Host`), causing severe memory bus saturation and excessive startup latency. Manual `-ngl 18` (for 96K) or `-ngl 20` (for 16K) is strictly superior.

---

## 4. 96K Context Benchmark & KV Cache Reuse
- **Context Size**: `-c 98304`, `-ngl 18`, `-ctk q8_0 -ctv q8_0 -fa on -b 2048 -t 6`
- **Cold Prompt Evaluation**:
  - Prompt Tokens: **30,225**
  - Prompt Processing Speed: **43.01 tok/s**
  - Time To First Token (TTFT): **702.72 s** (~11.7 min)
  - Generation Speed: **2.87 tok/s**
  - Peak VRAM: **20,399 MiB**
  - Peak RAM: **48,824 MiB**
- **Follow-up Turn 1 (KV Reuse Proof)**:
  - TTFT: **4.51 s** (Down from 702.7s — a **155x speedup**!)
  - Generation Speed: **3.16 tok/s**
  - KV Cache Reuse: **CONFIRMED (>99.9% prompt cache hit rate)**
- **Follow-up Turn 2**:
  - TTFT: **4.36 s**
  - Generation Speed: **3.42 tok/s**

---

## 5. Reasoning Controls & Chat Template
- **Reasoning Implementation**: Binary control via chat template (`enable_thinking: true | false`).
- **Thinking Enabled**: Verified. The model can generate explicit reasoning chains in `<think>...</think>` tags before emitting the final answer.
- **Thinking Suppression**: Verified. When requested or parameterized without thinking, `<think>` tags are omitted and direct concise responses are produced.
- **Effort Tiers**: Multi-tier levels (`low`/`medium`/`high`) are **NOT supported** natively by this model architecture.

---

## 6. Qualitative Agent Capabilities
- **Task A (Architecture / Planning)**: Model generated an exceptional distributed CDC event-driven architecture, detailing Kafka partition keys, Debezium CDC connectors, idempotency via Redis deduplication windows, and out-of-order handling via sequence numbers.
- **Task B (Code Audit / Review)**: Model identified the race condition across `await asyncio.sleep()`, uninitialized global connection pools, missing locks, and dictionary mutation hazards in concurrent asyncio coroutines.
- **Task C (Agentic Tool Calling)**: Model correctly emitted structured function tool calls matching OpenAI schema for `read_file` with arguments `file_path: '/etc/app/production.yaml'`.

---

## 7. Multimodal Vision Test
- **Projector**: `Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF-mmproj-Q8_0.gguf`
- **Status**: **PASS (Projector Load) / HOST_CPU_BOUND (Inference)**
- **Findings**:
  - The mmproj loads cleanly into host RAM using `--mmproj ... --no-mmproj-offload` (590.5 MiB model + 558.6 MiB compute buffer in host memory).
  - Executing multimodal vision transformer forward passes on CPU requires >5 minutes per image, mirroring the CPU vision bottleneck observed on Ornith-1.5. As instructed by user guidelines, long CPU vision tuning was stopped to preserve resources.
