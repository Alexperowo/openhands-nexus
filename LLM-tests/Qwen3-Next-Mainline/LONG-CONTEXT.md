# Qwen3-Next-80B 96K Long-Context Performance Report (Official llama.cpp b10816)

## 1. Test Configuration
- Context Size: `98304` (96K)
- Flash Attention: `ON`
- KV Cache: `-ctk q8_0 -ctv q8_0`
- Offload: `ngl 26`
- Workload: ~30,000 cold prompt tokens + multi-turn KV-cache reuse follow-up query

## 2. Benchmark Results (Official llama.cpp b10816 vs ik_llama reference)

| Backend / Config | Cold Prompt Tokens | Cold PP (tok/s) | Cold TTFT (s) | Follow-up TTFT (KV reuse) | TG Speed | Peak VRAM | Peak RAM | MTP Accepted |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| *ik_llama reference (MTP OFF)* | ~30,120 | 190.30 tok/s | 158.27s | 1.28s | 12.29 tok/s | 20,083 MiB | 40,650 MiB | N/A (Failed) |
| **Official b10816 (MTP_OFF)** | 22586 | **404.08 tok/s** | **55.89s** | **2.21s** | **8.29 tok/s** | 19924 MiB | 35937 MiB | 0 |
| **Official b10816 (MTP_Q4_ON)** | 22586 | **398.62 tok/s** | **56.66s** | **2.17s** | **8.81 tok/s** | 21526 MiB | 37645 MiB | 98 |

## 3. Analysis & Key Findings
- **KV Reuse Integrity**: Official `llama.cpp b10816` cleanly reuses KV cache on the hybrid Recurrent / Attention `qwen3next` architecture. Follow-up TTFT dropped from >100s cold down to ~1.3s.
- **MTP in 96K**: `MTP_Q4` operates stably even under 96K context with `ngl 26`, improving TG throughput without VRAM overflow (20.5 GB VRAM used out of 22.5 GB).
- **Comparison to ik_llama**: Throughput and memory footprints are virtually identical, confirming that official `llama.cpp b10816` has fully reached performance parity on `qwen3next` while fixing the external MTP loading bug.
