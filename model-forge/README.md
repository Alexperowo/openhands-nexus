# Model Forge — Workstation LLM Adaptation, Quantization & Fine-Tuning Lab

## 1. Project Charter & Mission
`model-forge` is the autonomous engineering laboratory for adapting, quantizing, calibrating, and optimizing frontier open-source LLMs specifically for the **OpenHands Nexus** workstation.

The primary engineering mission is **maximum hardware exploitation with minimum intelligence loss**:
1. Fitting large-parameter models (27B–80B) into strictly bound physical VRAM pools.
2. Unlocking concurrent dual-model execution across dual discrete GPUs (`GPU 0` + `GPU 1`).
3. Ensuring long-context residency (128K context = 131,072 tokens) without host RAM/CPU thrashing.
4. Preserving architecture-specific modules (Recurrent Gated DeltaNet states, Speculative MTP/Drafter heads) through mixed-precision tensor allocation.

---

## 2. Workstation Physical Ceilings (Absolute)

| Component | Physical Ceiling | Engineering Role |
| :--- | :--- | :--- |
| **System RAM** | Strictly **48 GB** (47.92 GB visible) | Model staging, GGUF quantization buffers, CPU offloading reserve |
| **GPU 0** | **NVIDIA GeForce RTX 5060 Ti (16 GB GDDR7)** | Isolated secondary model runner (Opus-Distill-v2 27B @ 128K ctx), fast memory bandwidth |
| **GPU 1** | **NVIDIA GeForce RTX 2080 Ti (22 GB GDDR6)** | Heavy primary model runner (Ornith 1.5-35B MTP @ 32K ctx, Tinfield 177B @ 16K ctx) |
| **Combined VRAM** | Strictly **37.9 GB** | Dual-GPU pooled or isolated concurrent allocation |
| **Storage (K:)** | Physical SSD partition | Station code, models, and runtime logs |
| **Storage (D:)** | High-capacity staging disk | Large BF16 weights downloads and raw imatrix datasets |

---

## 3. Directory Layout

```text
K:\Project\model-forge\
  ├── README.md                                # Project charter, ceilings, and operational manual
  ├── docs\
  │    ├── QWEN38_27B_ADAPTATION_SPEC.md       # Full architecture & quantization spec for Qwen3.8-27B
  │    ├── HARDWARE_BUDGET_CALCULATOR.md       # Universal memory formulas (KV, DeltaNet, Weights)
  │    └── QUANTIZATION_METHODOLOGY.md         # ik_llama flags, custom-q regexes, imatrix rules
  ├── recipes\
  │    ├── generate_custom_q.py                # AST/regex compiler from RCO allocation maps
  │    ├── qwen3.8_27b_rco_rules.txt           # 77-rule compiled recipe for Qwen3.8-27B IQ3_XXS-MTP
  │    ├── qwen3.8_27b_rco_iq3_s_rules.txt     # 69-rule compiled recipe for Qwen3.8-27B IQ3_S-MTP
  │    └── calibration_prompts\                # Calibrated prompts for domain-specific imatrix
  │         └── nexus_calibration_corpus.txt   # CodeAct, tool-use, Russian engineering corpus
  ├── scripts\
  │    ├── download_upstream.py                # Resumable HF downloader with checksum validation
  │    ├── quantize_candidate.py               # Automated pipeline (dry-run -> quantize -> verify)
  │    └── verify_vram_and_server.py           # Port 18005 isolated benchmark & VRAM validation
  └── calibration\
       └── README.md                           # Guidelines & index of importance matrix files (.gguf)
```

---

## 4. Current Workstation Objectives

### Objective A: Qwen3.8-27B-Opus-Distill-v2 Isolation on GPU 0
- **Problem:** Current `Q4_K_M` quant is 15.65 GB. With 128K context (KV cache = 2.95 GB) + DeltaNet state (75 MB) + CUDA scratchpad (0.95 GB), total VRAM footprint is 19.62 GB. This requires spilling to GPU 1 or host RAM, preventing concurrent dual-model execution.
- **Solution:** Produce Candidate B via Riemann Curvature Optimization (`IQ3_XXS-mtp` allocation map):
  - File size: **9.725 GiB (10.44 GB)** (~3.09 bpw).
  - Preserves 48 Gated DeltaNet layers via mixed IQ1/IQ2/IQ3/IQ4.
  - Elevates 16 full-attention layers and MTP Drafter head (`blk.64.nextn.eh_proj`) to `Q6_K`.
  - Fits 100% inside GPU 0 (16.00 GB VRAM) with **128K context (131,072 tokens)**.
  - Leaves GPU 1 (22 GB) 100% free for concurrent execution of Ornith 1.5-35B or large MoE subagents.

---

## 5. Standard Operating Procedures (SOP)

### Compiling Custom Quantization Recipes
```powershell
python recipes/generate_custom_q.py `
  --input "https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/raw/main/tensor-allocation/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.rco-allocation.txt" `
  --preserve-critical `
  --output-rules "recipes/qwen3.8_27b_rco_rules.txt"
```

### Dry-Running a Quantization Recipe
```powershell
python scripts/quantize_candidate.py `
  --src "K:\Project\Models\Qwen3.8\staging\Qwen3.8-27B-Opus-Distill-v2-BF16.gguf" `
  --dst "K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-RCO-IQ3_XXS-mtp.gguf" `
  --imatrix "calibration/imatrix-qwen3.8-27b.gguf" `
  --rules "recipes/qwen3.8_27b_rco_rules.txt" `
  --dry-run
```

### Validating VRAM Residency and MTP Speculative Head
```powershell
python scripts/verify_vram_and_server.py `
  --model "K:\Project\Models\Qwen3.8\Qwen3.8-27B-Opus-Distill-v2-RCO-IQ3_XXS-mtp.gguf" `
  --gpu 0 `
  --ctx 131072 `
  --ctk q6_0 `
  --ctv q4_0 `
  --spec-type "mtp:n_max=3,p_min=0.05"
```
