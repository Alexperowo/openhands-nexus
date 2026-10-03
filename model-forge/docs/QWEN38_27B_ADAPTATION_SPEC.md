# Technical Specification: Qwen3.8-27B-Opus-Distill-v2 Workstation Adaptation

## 1. Executive Summary & Hardware Goal
- **Model:** `Qwen3.8-27B-Opus-Distill-v2` (Gated DeltaNet hybrid architecture with Multi-Token Prediction drafter).
- **Target GPU:** `GPU 0` — **NVIDIA GeForce RTX 5060 Ti (16 GB GDDR7)**.
- **Target Operational Context:** **128K tokens (131,072 context window)**.
- **Station Architectural Goal:** Full isolation on GPU 0 with zero host RAM/CPU thrashing and zero footprint on GPU 1 (RTX 2080 Ti 22 GB), allowing concurrent dual-agent workflows (e.g. Ornith 1.5-35B executing tool tasks while Opus 27B audits code dumps and traces).

---

## 2. Grounded Physical GGUF Audit (`Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf`)

*Inspected directly from physical file `K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf`.*

### General Geometry
- **Total Tensors:** Exactly **866**.
- **Current File Size:** **15.646 GB** (14.57 GiB).
- **Block Breakdown:** 65 blocks total (`blk.0` through `blk.64`):
  - **Trunk Layers:** 64 blocks (`blk.0` .. `blk.63`).
    - **48 Gated DeltaNet Layers:** Linear recurrence layers with recurrent state tensors (`ssm_a`, `ssm_alpha`, `ssm_b`, `ssm_beta`, `ssm_dt`, `ssm_conv1d.weight`, `attn_gate.weight`, `attn_v.weight`).
    - **16 Full Attention Layers:** Standard quadratic self-attention layers with standard QKV and projection tensors (`attn_q`, `attn_k`, `attn_v`, `attn_output`).
  - **Drafter / MTP Head:** 1 block (`blk.64`).
    - Full-attention block geometry containing 4 distinct `nextn.*` tensors:
      - `blk.64.nextn.eh_proj.weight`
      - `blk.64.nextn.shared_head_norm.weight`
      - `blk.64.nextn_norm.weight`
      - `blk.64.nextn_q_norm.weight`

### Tensor Footprint Breakdown (Q4_K_M Baseline)

| Subsystem | Tensor Count | Current Quantization | Physical Size (GB) | Share (%) |
| :--- | :--- | :--- | :--- | :--- |
| **Gated DeltaNet Layers** | 336 | F32 (96), Q4_K (216), Q6_K (24) | 3.222 GB | 20.59% |
| **Full Attention Layers** | 68 | Q4_K (59), Q6_K (9) | 0.945 GB | 6.04% |
| **FFN Layers (MLP)** | 195 | Q4_K (gate/up), Q4_K/Q6_K (down) | 9.811 GB | 62.71% |
| **Token Embeddings** | 1 | `token_embd.weight` (Q4_K) | 0.666 GB | 4.26% |
| **Output Head** | 1 | `output.weight` (Q6_K) | 0.971 GB | 6.21% |
| **MTP Drafter Head** | 4 | `nextn.eh_proj` (Q4_K), norms (F32) | 0.028 GB | 0.18% |
| **Norms & Scalars** | 261 | F32 | 0.003 GB | 0.02% |
| **TOTAL** | **866** | — | **15.646 GB** | **100.0%** |

---

## 3. Physical VRAM Budgeting & Context Math (RTX 5060 Ti 16 GB)

### The Hybrid Architecture Advantage
Unlike standard Transformers where all 64 layers consume KV cache linearly with context length $C$:
$$\text{Layers with KV cache} = \mathbf{16\text{ layers}}\quad (\text{the 48 DeltaNet layers do not store KV cache}).$$

The 48 DeltaNet layers store an $O(1)$ constant hidden state vector regardless of context length:
$$\text{DeltaNet Memory} = 48 \times (\text{state\_dim} \times \text{head\_dim} \times \text{sizeof(FP32)}) \approx \mathbf{75\text{ MB}}.$$

### KV Cache Sizing for 16 Attention Layers at 128K Context (131,072 tokens)
- Key/Value dimension per head: 128
- Number of KV heads: 8 (Grouped Query Attention)
- Context length $C = 131,072$ tokens
- Number of Attention Layers $L = 16$

$$\text{KV Tokens} = 2 \times L \times N_{\text{kv\_heads}} \times D_{\text{head}} \times C = 2 \times 16 \times 8 \times 128 \times 131,072 = 4,294,967,296\text{ values}.$$

| KV Quantization Mode | Bits/Value | Total KV Cache Size (GiB) | Total KV Cache Size (GB) |
| :--- | :--- | :--- | :--- |
| **`-ctk f16 -ctv f16`** | 16.0 bits | 8.00 GiB | 8.59 GB |
| **`-ctk q8_0 -ctv q5_0`** | 6.5 bits | 3.25 GiB | 3.49 GB |
| **`-ctk q6_0 -ctv q4_0` (Optimal)** | 5.5 bits | **2.75 GiB** | **2.95 GB** |
| **`-ctk q4_0 -ctv q4_0`** | 4.0 bits | 2.00 GiB | 2.15 GB |

### Complete Dynamic Runtime Budget (128K Context)
1. **KV Cache (`-ctk q6_0 -ctv q4_0`):** 2.95 GB
2. **DeltaNet Recurrent Hidden States (48 layers):** 0.075 GB (75 MB)
3. **CUDA Runtime, FlashAttention Scratchpad & PyTorch/GGML Buffers:** ~0.95 GB
4. **Total Non-Weight Overhead:** $\mathbf{3.975\text{ GB}} \approx \mathbf{4.00\text{ GB}}$ (or 4.17 GB conservative).
5. **Physical VRAM Ceiling on RTX 5060 Ti:** Strictly **16.00 GB**.
6. **Maximum Safe Weight Allocation:** $16.00 - 4.17 = \mathbf{11.83\text{ GB}}$ (or $\mathbf{11.02\text{ GiB}}$).

---

## 4. Candidate Matrix & RCO Discovery

### Why Candidate A (Global IQ3_XXS) Fails Quality Requirements
Standard global quantization quantizes all weights indiscriminately to `IQ3_XXS` (~3.06 bpw). 
- Destroys the precision of DeltaNet transition gates (`ssm_dt`, `attn_gate`).
- Degrades `blk.64.nextn.eh_proj.weight`, collapsing speculative acceptance rate below 20%.
- Yields high perplexity penalty on multi-turn reasoning and code generation.

### Candidate B: Riemann Curvature Optimization (`IQ3_XXS-mtp`)
Discovered in `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`:
- Uses curvature information from the Hessian / Riemann metric to allocate bits where sensitivity is highest.
- Maps all **866 tensors** into heterogeneous quantization types:
  - FFN matrices (`down_proj`, `up_proj`, `gate_proj`) absorb the bulk of compression into `IQ1_M`, `IQ2_XXS`, `IQ2_XS`, `IQ3_XXS`.
  - Sensitive DeltaNet gates and full-attention projections are preserved in `IQ3_S`, `IQ4_XS`, `Q4_K`.
  - Output head (`output.weight`) preserved in `Q6_K`.
  - Embeddings (`token_embd.weight`) preserved in `Q4_K`.
  - MTP drafter head (`blk.64.nextn.eh_proj`) explicitly mapped to `Q6_K`.
- **Physical Verification Result:**
  - Dry-run return code: **0** (verified on station).
  - Target model file size: **9.725 GiB (10.44 GB)**.
  - VRAM with 128K context: $10.44 + 4.17 = \mathbf{14.61\text{ GB}} \le 16.00\text{ GB}$.
  - Leaves **1.39 GB VRAM safety buffer** on GPU 0.

### Candidate C: RCO + Nexus Agentic Domain imatrix
Further elevates Candidate B by calibrating on station-specific multi-turn agentic workloads:
- CodeAct loop traces (file editing, shell execution, diff evaluation).
- Complex Russian engineering reasoning and Russian dialogue.
- Tool call JSON formatting and schema obedience.

---

## 5. Blackwell RTX 5060 Ti Hardware Exploitation

1. **GDDR7 Memory Bandwidth (448–512 GB/s):**
   Generation of a 10.44 GB model on RTX 5060 Ti achieves $\approx 42\text{–}48\text{ tokens/sec}$ memory-bandwidth bound throughput, vs $\approx 25\text{–}28\text{ tokens/sec}$ on Ada Lovelace RTX 4060 Ti (288 GB/s).
2. **Native FP8 / FP4 Tensor Core Pipelines:**
   FlashAttention kernels with quantized KV cache execute without the unpacking penalties present on older architectures.
3. **MTP Drafter Acceleration:**
   Speculative acceptance of 2–3 tokens per step on `blk.64` multiplies effective generation speed to $> 70\text{ tokens/sec}$ in agentic reasoning loops.
