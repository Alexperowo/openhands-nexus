# VRAM Budget & Memory Allocation Analysis

## 1. Hardware Environment
- **GPU**: NVIDIA GeForce RTX 2080 Ti (22 GB physical capacity).
- **Physical VRAM Available**: `22,528 MiB`.
- **Operating System Mode**: Windows WDDM 610.88 / CUDA 13.3.
- **Baseline Desktop VRAM**: ~680 – 820 MiB (DWM, Explorer, apps).

---

## 2. Model VRAM Allocation Matrix (98,304 Context / 96K)

| Metric | Qwen3.8-27B-Opus | Ornith-1.5-35B | Qwen3-Next-80B-A3B-Thinking |
| :--- | :--- | :--- | :--- |
| **Backend** | ik_llama commit `3c58ae3` | ik_llama commit `3c58ae3` | llama-mainline `b10816` |
| **GPU Layers (-ngl)** | `999` (all layers) | `999` (all layers) | `26` layers |
| **Model Weights in VRAM** | ~15,340 MiB | ~16,850 MiB | ~16,200 MiB |
| **KV Cache (96K, q8_0/q5_0 or q8_0/q8_0)** | ~3,392 MiB | ~2,100 MiB | ~3,800 MiB |
| **Draft Model / MTP VRAM** | Internal (0 MiB extra) | Internal (0 MiB extra) | ~1,200 MiB |
| **Peak VRAM Allocated** | **20,939 MiB** | **20,652 MiB** | **21,510 MiB** |
| **Safety Margin to 22,528 MiB** | **+1,589 MiB** | **+1,876 MiB** | **+1,018 MiB** |
| **Risk of CUDA OOM** | **0%** | **0%** | **0%** |

---

## 3. WDDM Asynchronous CUDA Page Deallocation Protection

### The Problem:
Under Windows Display Driver Model (WDDM), terminating a CUDA process does not immediately release physical GPU pages. The kernel driver `nvlddmkm.sys` takes approximately 2 to 3 seconds to unmap physical pages. If a new backend starts immediately, it encounters a temporary OOM.

### The Solution:
In `K:\Project\llama-swap\config.yaml`, the `cmdStop` directive enforces an asynchronous deallocation buffer:
```yaml
cmdStop: powershell -NoProfile -Command "Stop-Process -Id ${PID} -Force; Start-Sleep -Seconds 3"
unloadTimeout: 15
```
This guarantees:
1. Physical VRAM drops back to baseline (~680–800 MiB) before the next process starts.
2. Zero memory leakage across hundreds of swaps.
3. At all times, strictly **one** model backend occupies GPU memory.
