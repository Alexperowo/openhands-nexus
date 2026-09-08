# Qwen3-Next-80B MTP Investigation & Benchmark Report

## 1. MTP Inventory
- **Target Model**: `K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf`
  - Size: 35,494,473,888 bytes (33.05 GiB)
  - Architecture: `qwen3next` (48 layers, MoE 512 experts / 10 active)
- **MTP Q4 Companion**: `K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf`
  - Size: 1,507,217,408 bytes (1.40 GiB)
  - Tensors: 23 tensors for block 48 (`blk.48.*`)
- **MTP Q6 Companion**: `K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q6_K.gguf`
  - Size: 1,873,725,440 bytes (1.74 GiB)
  - Tensors: 23 tensors for block 48 (`blk.48.*`)

---

## 2. Backend Compatibility & Root-Cause Analysis (`ik_llama` commit `3c58ae3`)

Both companion files were tested via `llama-server.exe` with `-m MAIN_MODEL -md MTP_FILE --spec-type mtp:n_max=1,p_min=0.0`.
Both failed during initial model initialization with return code `1`:

```
llama_model_load: error loading model: check_tensor_dims: tensor 'blk.0.attn_norm.weight' not found
llama_model_load_from_file: failed to load model
common_speculative_load_draft_model: failed to load draft model
```

### Direct Codebase Evidence in `ik_llama` commit `3c58ae3`:
1. **Missing Tensor Definitions for `qwen3next`**:
   In `src/llama-model.cpp` (lines 538-560), the architecture definition for `LLM_ARCH_QWEN3NEXT` lists standard attention/SSM tensors up to layer 47, but **omits `nextn` tensors** entirely (`blk.%d.nextn.eh_proj`, `blk.%d.nextn.enorm`, `blk.%d.nextn.hnorm`, `blk.%d.nextn.shared_head_norm`). During loading, `ik_llama` logs warnings:
   `Oops: got unknown for tensor blk.48.nextn.eh_proj.weight`.
2. **No MTP Computation Graph**:
   `src/graphs/build_qwen3next.cpp` builds only standard forward layers and has zero MTP graph logic (unlike `build_qwen35.cpp` and `build_step35.cpp`).
3. **Appended MTP Contract Exclusion**:
   In `src/common/speculative.cpp`:
   ```cpp
   static bool common_speculative_target_has_appended_mtp_contract(const llama_model * model) {
       return llama_model_is_step35(model) || llama_model_is_deepseek4(model) ||
              llama_model_is_qwen35_family(model);
   }
   ```
   `qwen3next` is explicitly absent from recognized appended MTP targets.
4. **Standalone Loader Requirement**:
   Because `qwen3next` is not registered as having an appended MTP companion contract, `ik_llama` routes `-md` through `common_speculative_load_draft_model`, expecting a full, standalone transformer model. Since the MTP files only contain layer 48 tensors, loader verification fails immediately when `blk.0.attn_norm.weight` is missing.

---

## 3. Decision & Winner

- **MTP Q4 Result**: `FAILED` (Backend loader incompatibility)
- **MTP Q6 Result**: `FAILED` (Backend loader incompatibility)
- **Winner**: **MTP OFF**
- **Recommended ngl**: **26**
  - Leaves 2.4+ GiB VRAM headroom on RTX 2080 Ti 22GB.
  - Generates 16.5 - 17.5 tok/s at 16K context and ~12.5 - 13.3 tok/s at 96K context.
