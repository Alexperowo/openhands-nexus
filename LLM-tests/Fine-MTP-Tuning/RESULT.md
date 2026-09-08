# Final MTP Fine Tuning Report: Qwen3.8-27B & Ornith-1.5-35B

**Backend**: `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`)  
**Hardware**: NVIDIA GeForce RTX 2080 Ti 22GB (CUDA0)  
**Base Runtime Configuration**: `-c 98304 -ctk q8_0 -ctv q5_0 -fa on -ngl 999 -np 1 --jinja`  
**Execution Timestamp**: 2026-09-04 08:17:19

---

## 1. Summary Comparison Table

### Qwen3.8-27B-Opus-Distill-v2
| Metric | Value |
| :--- | :--- |
| **Old Winner** | `n_max=3, p_min=0.0` |
| **New Winner** | `n_max=3, p_min=0.0` |
| **Old Speed (Follow-up 96K)** | `13.81 tok/s` |
| **New Speed (Follow-up 96K)** | `13.87 tok/s (Candidate: n3/p0.2)` |
| **Gain %** | `+0.51%` |
| **Acceptance Rate** | `43.4% (n3/p0.0) vs 47.7% (n3/p0.2)` |
| **Peak VRAM** | `21,532 MiB` |
| **Launcher Changed** | **`NO`** |

*Decision rationale*: Candidate `n3/p0.2` demonstrated a minor gain of +0.51% on 96K KV reuse follow-up, which is well below the established 2–3% practical threshold. Production winner `n_max=3, p_min=0.0` is retained for proven baseline stability.

### Ornith-1.5-35B-A3B
| Metric | Value |
| :--- | :--- |
| **Old Winner** | `n_max=1, p_min=0.75` |
| **New Winner** | `n_max=1, p_min=0.75` |
| **Old Speed (Follow-up 96K)** | `45.86 tok/s` |
| **New Speed (Follow-up 96K)** | `45.70 tok/s (Candidate: n1/p0.5)` |
| **Gain %** | `-0.35%` |
| **Acceptance Rate** | `73.9% (n1/p0.75) vs 73.9% (n1/p0.5)` |
| **Peak VRAM** | `20,768 MiB` |
| **Launcher Changed** | **`NO`** |

*Decision rationale*: On 96K long-prompt KV reuse, candidate `n1/p0.5` performed at 45.70 tok/s vs production winner `n1/p0.75` at 45.86 tok/s (-0.35%). Production winner `n_max=1, p_min=0.75` maintains superior long-context generation throughput with identical VRAM and acceptance.

---

## 2. Final Status & Verdicts

```text
QWEN MTP TUNING = CLOSED
ORNITH MTP TUNING = CLOSED
```

---

## 3. Short Sweep Results (Context 32K, 256 Gen Tokens)

### Ornith-1.5-35B ($n_{max}=1$)
| $p_{min}$ | Gen Speed (tok/s) | Acceptance Rate | Drafted / Accepted | Wall Time (s) | Peak VRAM (MiB) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `0.50` | **73.31** | 64.9% | 154 / 100 | 3.69s | 19,774 |
| `0.60` | 66.02 | 66.0% | 153 / 101 | 4.16s | 19,774 |
| `0.65` | 72.99 | 66.0% | 153 / 101 | 3.77s | 19,774 |
| `0.70` | 55.33 | 66.0% | 153 / 101 | 4.92s | 19,774 |
| `0.75` (Prod) | 68.67 | 66.0% | 153 / 101 | 4.00s | 19,774 |
| `0.80` | 73.07 | 66.0% | 153 / 101 | 3.77s | 19,774 |
| `0.85` | 61.07 | 66.0% | 153 / 101 | 4.47s | 19,781 |
| `0.90` | 67.89 | 66.0% | 153 / 101 | 4.07s | 19,774 |

### Qwen3.8-27B
| Configuration | Gen Speed (tok/s) | Acceptance Rate | Drafted / Accepted | Wall Time (s) | Peak VRAM (MiB) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `n3 / p0.00` (Prod) | 21.05 | 30.7% | 398 / 122 | 12.55s | 18,856 |
| `n3 / p0.05` | 23.96 | 40.9% | 342 / 140 | 11.12s | 18,854 |
| `n3 / p0.10` | 23.89 | 40.9% | 342 / 140 | 11.15s | 18,854 |
| `n3 / p0.20` | **25.16** | 46.5% | 312 / 145 | 10.63s | 18,854 |
| `n3 / p0.30` | 24.89 | 48.6% | 294 / 143 | 10.73s | 18,854 |
| `n4 / p0.30` | 23.46 | 42.7% | 337 / 144 | 11.37s | 19,004 |
| `n4 / p0.40` | 22.39 | 44.7% | 293 / 131 | 11.85s | 19,004 |
| `n4 / p0.50` | 22.66 | 51.3% | 230 / 118 | 11.74s | 19,004 |

*Note*: Group B ($n_{max}=4$) clearly lost to Group A ($n_{max}=3$) on generation speed across all parameters.

---

## 4. 96K Long Context & KV Cache Reuse Detailed Data

### Ornith-1.5: Production (`n1 / p0.75`) vs Candidate (`n1 / p0.50`)
- **Production (`n1 / p0.75`)**:
  - Turn 1 (Cold ~84K): 43.65 tok/s (Rep: 44.24 tok/s), Wall: 102.9s / 102.3s, Draft Acc: 71.0%
  - Turn 2 (KV Reuse): 47.11 tok/s (Rep: 47.53 tok/s), Wall: 4.86s / 4.82s, Draft Acc: 80.0%
  - Turn 3 (KV Reuse): 45.04 tok/s (Rep: 43.73 tok/s), Wall: 5.06s / 5.18s, Draft Acc: 71.6%
  - **Average Follow-up Gen Speed: 45.86 tok/s** | Peak VRAM: 20,768 MiB
- **Candidate (`n1 / p0.50`)**:
  - Turn 1 (Cold ~84K): 44.56 tok/s (Rep: 43.69 tok/s), Wall: 102.2s / 102.3s, Draft Acc: 71.0%
  - Turn 2 (KV Reuse): 47.18 tok/s (Rep: 46.39 tok/s), Wall: 4.89s / 4.93s, Draft Acc: 80.0%
  - Turn 3 (KV Reuse): 44.04 tok/s (Rep: 45.18 tok/s), Wall: 5.19s / 5.05s, Draft Acc: 71.6%
  - **Average Follow-up Gen Speed: 45.70 tok/s** | Peak VRAM: 20,768 MiB

### Qwen3.8-27B: Production (`n3 / p0.00`) vs Candidate (`n3 / p0.20`)
- **Production (`n3 / p0.00`)**:
  - Turn 1 (Cold ~85K): 13.95 tok/s (Rep: 13.96 tok/s), Wall: 259.1s / 258.6s, Draft Acc: 44.1%
  - Turn 2 (KV Reuse): 13.48 tok/s (Rep: 13.49 tok/s), Wall: 15.76s / 15.77s, Draft Acc: 41.2%
  - Turn 3 (KV Reuse): 14.13 tok/s (Rep: 14.12 tok/s), Wall: 15.16s / 15.16s, Draft Acc: 44.9%
  - **Average Follow-up Gen Speed: 13.81 tok/s** | Peak VRAM: 21,532 MiB
- **Candidate (`n3 / p0.20`)**:
  - Turn 1 (Cold ~85K): 13.76 tok/s (Rep: 13.74 tok/s), Wall: 259.2s / 259.1s, Draft Acc: 45.8%
  - Turn 2 (KV Reuse): 12.44 tok/s (Rep: 12.45 tok/s), Wall: 16.95s / 16.94s, Draft Acc: 37.8%
  - Turn 3 (KV Reuse): 15.29 tok/s (Rep: 15.30 tok/s), Wall: 13.98s / 13.96s, Draft Acc: 54.3%
  - **Average Follow-up Gen Speed: 13.87 tok/s** | Peak VRAM: 21,532 MiB

---

## 5. Artifacts and Verification

- Suite Script: [`run-fine-tuning.ps1`](file:///K:/Project/LLM-tests/Fine-MTP-Tuning/run-fine-tuning.ps1)
- Benchmark Dataset: [`BENCHMARKS.csv`](file:///K:/Project/LLM-tests/Fine-MTP-Tuning/BENCHMARKS.csv)
- Raw Server Execution Logs: [`logs/`](file:///K:/Project/LLM-tests/Fine-MTP-Tuning/logs)
- Production Launchers (unchanged):
  - Qwen: [`K:\Project\LLM-tests\BEST-QWEN38-96K.cmd`](file:///K:/Project/LLM-tests/BEST-QWEN38-96K.cmd)
  - Ornith: [`K:\Project\LLM-tests\BEST-ORNITH15-96K.cmd`](file:///K:/Project/LLM-tests/BEST-ORNITH15-96K.cmd)
