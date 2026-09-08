# Laguna S 2.1 Optimization & Benchmark Report

## 1. Executive Summary
- **Model**: `D:\AI\Models\Laguna-S-2.1-UD-IQ3_S.gguf` (48,428,911,520 bytes ≈ 48.4 GB).
- **Architecture**: `laguna` (40 blocks, Yarn RoPE scaling, native context 262,144).
- **Backend**: `D:\Project\poolside-llama-laguna-current\llama-server.exe` (commit `06f8ceb`).
- **DFlash Accelerators**:
  - Q4_K: `D:\AI\Models\laguna-s-2.1-DFlash-Q4_K.gguf` (652 MiB).
  - BF16: `D:\AI\Models\Laguna-S-2.1-DFlash-BF16.gguf` (2.23 GiB).
- **Optimal Hardware Configuration**:
  - **Best GPU Offload (`-ngl`)**: `18`
  - **Best DFlash Setting**: `bf16` with `--spec-draft-n-max 3`
  - **No-DFlash Generation Speed**: **3.98 tok/s**
  - **Best DFlash Generation Speed**: **3.54 tok/s**
  - **DFlash Acceleration**: **-11.1%**
  - **Peak VRAM**: `18903 MiB`
  - **Peak System RAM**: `47519 MiB`

---

## 2. GPU Offload Sweep Comparison (Context = 16384, DFlash OFF)

| Mode | ngl | Prompt tok/s | Gen tok/s | TTFT (s) | Wall (s) | Peak VRAM (MiB) | Peak RAM (MiB) | Status |
|---|---|---|---|---|---|---|---|---|
| coarse_sweep | 8 | 5.582234459087747 | 3.583096027869321 | 8.777847 | 80.24715423583984 | 9129 | 46913 | PASS |
| coarse_sweep | 11 | 5.098439419718517 | 3.3158607333310965 | 9.610783999999999 | 86.85114049911499 | 12067 | 47236 | PASS |
| coarse_sweep | 13 | 5.2525501130799 | 3.459977380668185 | 9.328802 | 83.34154009819031 | 14039 | 47344 | PASS |
| coarse_sweep | 15 | 5.583397210056177 | 3.628188461941182 | 8.776019 | 79.34948444366455 | 15967 | 47315 | PASS |
| fine_sweep | 16 | 5.377891247624673 | 3.8143917567179746 | 9.111378 | 76.2408139705658 | 16931 | 47459 | PASS |
| coarse_sweep | 17 | 5.439309736053611 | 3.912803599742629 | 9.008496 | 74.45709085464478 | 17939 | 47359 | PASS |
| fine_sweep | 18 | 5.504115168555102 | 3.9790228402749976 | 8.90243 | 73.26183152198792 | 18903 | 47519 | PASS |

---

## 3. DFlash Speculative Decoding Optimization (ngl=18)

| DFlash Quant | Draft N Max | Drafted | Accepted | Acceptance % | Gen tok/s | Prompt tok/s | Wall (s) | Peak VRAM | Status |
|---|---|---|---|---|---|---|---|---|---|
| None (Baseline) | 0 | 0 | 0 | 0.0% | 3.98 | 5.504115168555102 | 73.26183152198792 | 18903 | PASS |
| Q4_K | 3 | 393 | 124 | 31.6% | 3.478244376259683 | 4.566956948042476 | 84.35244107246399 | 19753 | PASS |
| Q4_K | 5 | 615 | 132 | 21.5% | 2.9579593897826837 | 5.20288545656541 | 96.01692152023315 | 19753 | PASS |
| Q4_K | 7 | 824 | 135 | 16.4% | 2.5806016656654736 | 5.234816787822406 | 108.59070062637329 | 19753 | PASS |
| Q4_K | 10 | 1269 | 127 | 10.0% | 1.9346971835018487 | 5.626043760286905 | 141.058696269989 | 19753 | PASS |
| Q4_K | 14 | 1781 | 122 | 6.9% | 1.5348037432664232 | 5.080836629223666 | 176.46463012695312 | 19753 | PASS |
| BF16 | 3 | 390 | 124 | 31.8% | 3.5369637023521245 | 3.7148130444522867 | 85.59063696861267 | 21267 | PASS |

---

## 4. 96K Target Context Benchmark (`-c 98304`, `-ngl 18`, DFlash=bf16)

### Cold Long Prompt Evaluation (~30K tokens)
- **Prompt Tokens**: 28681
- **Prompt Processing Speed**: **101.92769142741703 tok/s**
- **Time To First Token (TTFT)**: **281.38575099999997 s**
- **Generation Speed**: **1.1724949037234205 tok/s**
- **Peak VRAM**: 22146 MiB
- **Peak System RAM**: 48823 MiB
- **Wall Time**: 499.8227984905243 s

### Follow-up Turn 1 (KV Reuse Proof)
- **Prompt Tokens Evaluated**: **28959** (Previous prompt was 100% cached)
- **Follow-up TTFT**: **9.845897 s**
- **Generation Speed**: **1.3461372014585817 tok/s**
- **Wall Time**: 105.08709716796875 s

### Follow-up Turn 2
- **Prompt Tokens Evaluated**: **29107**
- **Generation Speed**: **1.051686010427617 tok/s**
- **Wall Time**: 49.03426170349121 s
