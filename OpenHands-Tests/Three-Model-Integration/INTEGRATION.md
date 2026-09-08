# Production Integration Architecture: Qwen27 + Ornith + Qwen3-Next

## 1. Executive Summary & Objective
This document formalizes the production integration of the three-model architecture inside OpenHands using `llama-swap`:
1. **`Qwen3.8-27B-Opus`**: Planner, Lead Architect, Normal Reviewer, Router.
2. **`Ornith-1.5-35B`**: Executor, Coding Agent, Terminal / Tools, Vision.
3. **`Qwen3-Next-80B-A3B-Thinking`**: Heavy / Deep Reviewer for deep reasoning, subtle concurrency/race conditions, and autonomous escalation.

---

## 2. Model & Backend Matrix

| Role | Model Name | Quant / GGUF | Backend Binary | Context | KV Quant | Draft / Speculative | Max VRAM |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Planner / Architect / Reviewer** | Qwen3.8-27B-Opus | Distill-v2 Q4_K_M (16.2 GB) | `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`) | 98,304 (96K) | CTK q8_0, CTV q5_0 | Internal MTP (`n_max=3, p_min=0.0`) | **20,939 MiB** |
| **Executor / Coding / Vision** | Ornith-1.5-35B | MTP-19G-ICE (19.8 GB) | `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`) | 98,304 (96K) | CTK q8_0, CTV q5_0 | Internal MTP (`n_max=1, p_min=0.75`) | **20,652 MiB** |
| **Heavy / Deep Reviewer** | Qwen3-Next-80B-A3B-Thinking | UD-Q3_K_XL (35.5 GB) | `K:\Project\llama-mainline\b10816\llama-server.exe` (commit `427291b5b`) | 98,304 (96K) | CTK q8_0, CTV q8_0 | External MTP Draft `Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf` (`--spec-type draft-mtp --spec-draft-n-max 1`) | **21,510 MiB** |

> [!IMPORTANT]
> **Why Mainline `b10816` for Qwen3-Next:**
> `ik_llama` (commit `3c58ae3`) does not support external MTP draft models for Qwen3-Next MoE architecture and lacks the reasoning budget control flags. Mainline `b10816` provides verified MTP draft speculative decoding (acceptance rate ~86-90%, ~19.8 t/s generation speed) and `--reasoning-budget-message` stop injection.

---

## 3. Router Configuration (`llama-swap`)
Config path: `K:\Project\llama-swap\config.yaml`
- **Listening Interface**: `http://127.0.0.1:8080`
- **Health Check Timeout**: `1200` seconds (accommodates completely cold reads from external USB drive `K:` without premature eviction).
- **Direct IP Proxying**: `proxy: http://127.0.0.1:${PORT}` (bypasses Windows IPv6 localhost resolution delays).
- **Graceful WDDM CUDA VMM Release**:
  ```yaml
  cmdStop: powershell -NoProfile -Command "Stop-Process -Id ${PID} -Force; Start-Sleep -Seconds 3"
  unloadTimeout: 15
  ```
  *Rationale*: Under Windows Display Driver Model (WDDM), `nvlddmkm.sys` releases physical GPU memory pages asynchronously over ~2-3 seconds. The 3-second sleep ensures VRAM returns to baseline (<900 MiB) before the incoming backend allocates CUDA buffers.

---

## 4. Ownership Isolation & Safety Guarantees
- `start-swap.ps1`:
  - Checks if port 8080 is already occupied.
  - If occupied and healthy: records `owned: false` in `session.json`.
  - If launched by this session: records `owned: true` and the exact PID.
- `stop-swap.ps1`:
  - If `owned == false`: skips stopping, preserving external/foreign services.
  - If `owned == true`: requests graceful model unload via API, then terminates ONLY the owned llama-swap process and its recorded child processes.
  - Never executes mass process killing (`taskkill /IM` or process-name based killing is forbidden).
