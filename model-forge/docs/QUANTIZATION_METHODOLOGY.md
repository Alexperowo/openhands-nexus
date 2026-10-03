# Workstation Quantization Methodology & Toolchain Reference

## 1. Physical Toolchain
- **Quantization Engine:** `K:\Project\ik_llama\bin\llama-quantize.exe` (Mainline GGML/GGUF with IK/CUDA 12.8 extensions).
- **Calibration Engine:** `K:\Project\ik_llama\bin\llama-imatrix.exe`.
- **Inference Server:** `K:\Project\ik_llama\bin\llama-server.exe`.

---

## 2. Syntax & Type Formatting Rules (Strict)

The `llama-quantize.exe` binary enforces strict case sensitivity in `--custom-q`:

### Standard K-Quantizers (Must use capital `K`)
- `q2_K`
- `q3_K`
- `q4_K`
- `q5_K`
- `q6_K`
- `q8_0` (legacy 8-bit quantized block)

### I-Matrix / Importance Quantizers (Must use lowercase `iq`)
- `iq1_s`, `iq1_m`
- `iq2_xxs`, `iq2_xs`, `iq2_s`, `iq2_m`
- `iq3_xxs`, `iq3_xs`, `iq3_s`, `iq3_m`
- `iq4_xs`, `iq4_nl`

*Attempting to specify `IQ3_XXS` or `q4_k` will cause `llama-quantize.exe` to fail with unrecognized quant type.*

---

## 3. Critical Flags & Behavioral Semantics

### `--custom-q <comma-separated-rules>`
Overrides the default quantization scheme on a per-tensor basis. Supports regular expressions:
```text
blk\.(0|1|2)\.attn_q\.weight=q6_K,blk\..*\.ffn_down\.weight=iq2_xxs,output\.weight=q6_K
```
*Note on Windows CLI:* Command-line strings exceeding 32,767 characters will fail. Use regex grouping (`blk\.(1|2|3)\...`) rather than expanding 866 tensors individually.

### `--imatrix <path/to/imatrix.gguf>`
Mandatory whenever any tensor is assigned an `iq*` type.
- `llama-quantize` uses the activation statistics in the imatrix file to compute the optimal codebook indices.
- Omission of `--imatrix` when IQ quants are present causes immediate termination: `Missing importance matrix... bailing out`.

### `--ignore-imatrix-rules`
By default, `llama-quantize` attempts to apply internal heuristics linking certain tensor types to specific quantization floors based on the imatrix.
- When applying custom RCO or Unsloth Dynamic V3 maps, `--ignore-imatrix-rules` must be provided to ensure the user's `--custom-q` assignments take absolute precedence.

### `--allow-requantize`
Permits quantizing a file whose tensors are already quantized (e.g. from `Q4_K_M` to `IQ3_XXS`).
- **CRITICAL WORKSTATION RULE:** Never use `--allow-requantize` for production candidate weights! Re-quantization compounds quantization noise and irreversibly degrades perplexity. Only use `--allow-requantize` in conjunction with `--dry-run` to verify tensor layout and memory budgeting. Production models must strictly be quantized from pristine `BF16` or `FP16` source checkpoints.

### `--dry-run`
Simulates the entire quantization pipeline without writing tensor data to disk.
- Validates regex syntax, tensor matching, imatrix availability, and produces the exact predicted file size and compression ratio.
- Essential verification gate before launching multi-hour quantization jobs.

---

## 4. The MTP (Multi-Token Prediction) Drafter Dilemma

In hybrid models such as `Qwen3.8-27B` and `Qwen3-Next-80B`, speculative decoding is performed by an integrated drafter block (`blk.64` or `blk.80`).
- **The Issue:** Standard forward passes in `llama-imatrix` execute trunk attention layers and skip speculative drafter heads during calibration. Consequently, the imatrix contains no activation norms for `blk.64.nextn.*`.
- **The Failure Mode:** If left to automatic quantizers, drafter heads either fall back to uncalibrated low-bit quantizations or cause errors, destroying speculative acceptance rates.
- **The Solution:** In all custom recipes, explicitly pin `blk.64.nextn.eh_proj.weight` to `q6_K` or `q8_0`. Because the entire MTP head is less than 28 MB, keeping it at high precision costs negligible VRAM while preserving $> 70\%$ drafter acceptance.
