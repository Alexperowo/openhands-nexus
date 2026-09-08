# Qwen3-Next-80B-A3B-Thinking Optimization & Benchmark Report

## 1. Executive Summary
- **Model**: `K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf` (35,494,473,888 bytes ≈ 33.05 GiB).
- **Architecture**: `qwen3next` (MoE: 48 layers + 1 output, 512 total experts, 10 active experts per token = ~3B active params, native context 262,144).
- **Backend**: `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`).
- **MTP Status**: **NOT AVAILABLE / NOT USED** (0 speculative tensor keys in GGUF metadata).
- **Optimal Hardware Configuration**:
  - **Best GPU Offload (`-ngl`) for 16K**: `30` (Peak VRAM: `22069 MiB`, TG: **19.33 tok/s**).
  - **Best GPU Offload (`-ngl`) for 96K**: `26` (Safe headroom for 96K KV cache).
  - **Peak System RAM**: `39143 MiB` (fits comfortably in 48GB physical RAM).

---

## 2. GPU Offload Sweep Comparison (Context = 16384)

| Mode | ngl | Prompt tok/s | Gen tok/s | TTFT (s) | Wall (s) | Peak VRAM (MiB) | Peak RAM (MiB) | Status |
|---|---|---|---|---|---|---|---|---|
| coarse_sweep | 18 | 31.26386582510753 | 13.006491712756306 | 1.663262 | 21.395272731781006 | 14008 | 38937 | PASS |
| coarse_sweep | 22 | 63.82600050324346 | 14.220576585498469 | 0.8147150000000001 | 18.83369469642639 | 16760 | 38912 | PASS |
| coarse_sweep | 25 | 69.30625768866295 | 16.477967123494704 | 0.750293 | 16.330422401428223 | 18894 | 38925 | PASS |
| coarse_sweep | 28 | 73.31585032287173 | 17.828388114537923 | 0.70926 | 15.095338582992554 | 20946 | 38884 | PASS |
| fine_sweep | 29 | 76.80809202791089 | 18.2402608585306 | 0.677012 | 14.742485761642456 | 21552 | 38974 | PASS |
| coarse_sweep | 30 | 49.29461304676732 | 19.33098773947205 | 1.054882 | 14.326356410980225 | 22069 | 39143 | PASS |
| fine_sweep | 31 | 46.29786264136429 | 11.782334442207489 | 1.123162 | 22.880149602890015 | 22069 | 39820 | PASS |

---

## 3. 96K Target Context Benchmark (`-c 98304`, `-ngl 26`)

### Cold Long Prompt Evaluation (~30K tokens)
- **Prompt Tokens**: 30120
- **Prompt Processing Speed**: **190.30175983258295 tok/s**
- **Time To First Token (TTFT)**: **158.274942 s**
- **Generation Speed**: **12.286822430938217 tok/s**
- **Peak VRAM**: 20083 MiB
- **Peak System RAM**: 40650 MiB
- **Wall Time**: 179.2429871559143 s

### Follow-up Turn 1 (KV Reuse Proof)
- **Prompt Tokens Evaluated**: **30142** (Previous prompt was 100% cached)
- **Follow-up TTFT**: **1.2844980000000001 s**
- **Generation Speed**: **12.498322978928414 tok/s**
- **Wall Time**: 11.626607894897461 s

### Follow-up Turn 2
- **Prompt Tokens Evaluated**: **30163**
- **Generation Speed**: **13.316169345886875 tok/s**
- **Wall Time**: 6.304012775421143 s
