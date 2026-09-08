# NEW PRODUCTION ARCHITECTURE & MASTER PLAN
**Project**: OpenHands Production Station (Qwen + Ornith + Next)
**Date**: 2026-09-05
**Status of Previous Plans**: All previous `implementation_plan.md` drafts and 17-gate monolithic schemes are hereby marked as **DEPRECATED / REJECTED**.
**Current Plan Status**: **APPROVED WITH 4 AMENDMENTS**.

---

## 1. Goal & Architecture Overview

The objective is to establish a daily-driver OpenHands production station utilizing three frozen local models:
1. **Qwen3.8-27B-Opus** (`ik_llama commit 3c58ae3`): Planner, Architect, Routine Reviewer, Router, and General Conversationalist.
2. **Ornith-1.5-35B** (`ik_llama commit 3c58ae3`): Executor, Coding, Tools/Terminal execution, Android MCP, Vision.
3. **Qwen3-Next-80B-A3B-Thinking** (`official llama.cpp b10816`): Heavy Reviewer, Deep Debugger, Architecture Escalation.

### Architectural Flexibility Without Backend Duplication
The station does **not** lock the user into a single hardcoded trio. It supports:
- **Standalone Access**: The user can run any single model in isolation.
- **Alternative Pairings**: The user can select specific two-model combinations.
- **Full Team Mode**: The user can run the automated team (Default Mode).

All modes reuse the **exact same single set of backend definitions** in `K:\Project\llama-swap\config.yaml` (`qwen`, `ornith`, `next` on `http://127.0.0.1:8080/v1`).

---

## 2. Current State Physical Inspection & Strict Classification

| Component / Artifact | File Location | Strict Status | Physical Evidence & Details |
|---|---|:---:|---|
| **qwen llama-swap entry** | `K:\Project\llama-swap\config.yaml` | `VERIFIED_CURRENT` | Target exe `K:\Project\ik_llama\bin\llama-server.exe` exists; GGUF model `D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf` exists; flags: MTP n_max=3, context=98304, ctk=q8_0, ctv=q5_0, ngl=999. Tested in prior session. |
| **ornith llama-swap entry** | `K:\Project\llama-swap\config.yaml` | `VERIFIED_CURRENT` | Target exe `K:\Project\ik_llama\bin\llama-server.exe` exists; GGUF model `K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf` exists; flags: MTP n_max=1, context=98304, ctk=q8_0, ctv=q5_0, ngl=999. Tested in prior session. |
| **next llama-swap entry** | `K:\Project\llama-swap\config.yaml` | `VERIFIED_CURRENT` | Target exe `K:\Project\llama-mainline\b10816\llama-server.exe` exists; GGUF base + draft MTP Q4_K_M exists; flags: draft-mtp n_max=1, ngl=26, FA=on, context=98304, ctk=q8_0, ctv=q8_0, `--reasoning-format deepseek`. Tested in prior session. |
| **Standalone model profiles** | `C:\Users\User\.openhands\profiles\` | `VERIFIED_CURRENT` | Files exist on disk: `Qwen38_Opus_96K.json`, `Ornith-Coding.json`, `Next-Normal.json`, `Next-Deep.json`, etc. |
| **Standalone model selection/execution through OpenHands** | OpenHands Web UI / Runtime | `EXISTS_BUT_NOT_VERIFIED` | Profile files exist on disk, but actual selection, runtime loading, and query execution through real OpenHands requests are not yet verified. Must be verified in Stage 1. |
| **Next-Normal profile configuration** | `C:\Users\User\.openhands\profiles\Next-Normal.json` | `EXISTS_BUT_NOT_VERIFIED` | Targets `openai/next`. Contains redundant `reasoning_budget_tokens: 2048` alongside `thinking_budget_tokens: 2048`. Pass-through via OpenHands request not yet verified. |
| **Next-Deep profile configuration** | `C:\Users\User\.openhands\profiles\Next-Deep.json` | `EXISTS_BUT_NOT_VERIFIED` | Targets `openai/next`. Contains redundant `reasoning_budget_tokens: 4096` alongside `thinking_budget_tokens: 4096`. Pass-through via OpenHands request not yet verified. |
| **SwitchLLMTool availability** | `openhands.sdk.tool.builtins.switch_llm` | `VERIFIED_CURRENT` | Present in installed `openhands-sdk` package; enabled in `C:\Users\User\.openhands\settings.json` via `"enable_switch_llm_tool": true`. |
| **START / STOP scripts** | `K:\Project\` & `K:\Project\.openhands-local\` | `VERIFIED_CURRENT` | `START-OPENHANDS-LOCAL.cmd`, `STOP-OPENHANDS-LOCAL.cmd`, `start.ps1`, `stop.ps1`, `diagnostics.ps1` exist. Manage ports 8000, 8080, 18000, 18001, 18002. |
| **Ownership mechanism** | `K:\Project\.openhands-local\start.ps1` | `VERIFIED_CURRENT` | Tracks `swap_owned`, `canvas_owned`, `voice_owned` and exact PIDs in `session.json`. `stop.ps1` only stops owned PIDs and ignores foreign instances. |
| **Current routing/orchestration** | `K:\Project\OpenHands-Tests\` | `EXISTS_BUT_NOT_VERIFIED` | Prototype script `run_e2e_scenarios.py` exists, but production routing policies need formalization. |
| **Team/Preset selection mechanism** | OpenHands Runtime | `MISSING` | Supported implementation mechanism must be discovered before implementation. |

---

## 3. Target User Experience & Mode Architecture

The station will expose selectable modes in OpenHands without duplicating model files or backend instances:

### A. Standalone Modes
1. **`MODE: Qwen Standalone`** (Planning, architecture, general coding)
2. **`MODE: Ornith Standalone`** (Terminal execution, code modification, fast tools)
3. **`MODE: Next-Normal`** (Deep code review, architecture, budget: 2048)
4. **`MODE: Next-Deep`** (Exhaustive debugging, concurrency, budget: 4096)

### B. Team Modes
5. **`MODE: Team Qwen + Ornith`** (Qwen Planner/Reviewer + Ornith Executor via SwitchLLMTool)
6. **`MODE: Team Next + Ornith`** (Next Heavy Architect + Ornith Executor)
7. **`MODE: Team Qwen + Next`** (Qwen routine + Next deep review)
8. **`MODE: Full Team (Default)`** (Qwen Planner -> Ornith Executor -> Qwen Reviewer -> Next Escalation upon 2 failures)

---

## 4. Master Plan: Five Independent Stages

```mermaid
graph LR
    Stage1[Stage 1: Baseline & Standalone] -->|STOP + Approval| Stage2[Stage 2: Qwen + Ornith Workflow]
    Stage2 -->|STOP + Approval| Stage3[Stage 3: Team Presets & Next]
    Stage3 -->|STOP + Approval| Stage4[Stage 4: Automated Heavy Escalation]
    Stage4 -->|STOP + Approval| Stage5[Stage 5: Lifecycle & Production Sign-Off]
```

### STAGE 1: Baseline Workstation & Standalone Access to All 3 Models
- **Objective**: Prove real OpenHands execution for all three standalone models (`qwen`, `ornith`, `next`) and verify genuine `thinking_budget_tokens` pass-through for Next-Normal (2048) and Next-Deep (4096) with zero physical server reload.
- **Actions**:
  1. Clean `Next-Normal.json` and `Next-Deep.json`: remove unproven `reasoning_budget_tokens`; retain strictly `thinking_budget_tokens: 2048` and `4096` in `litellm_extra_body`.
  2. Launch `llama-swap` on `:8080` (tracked ownership).
  3. Dispatch real OpenHands requests to `Qwen38_Opus_96K` and verify real model completion.
  4. Dispatch real OpenHands requests to `Ornith-Coding` and verify real model completion.
  5. Dispatch real OpenHands requests to `Next-Normal` and capture raw server log proving `thinking_budget_tokens: 2048` was received by `llama-server`.
  6. Dispatch real OpenHands requests to `Next-Deep` and capture raw server log proving `thinking_budget_tokens: 4096` was received by `llama-server`.
  7. Verify `llama-server` process PID is identical between Normal and Deep (zero physical reload).
  8. Verify `finish_reason=stop`, `reasoning_content` present, and final `content` present.
- **Gate**: `STAGE_1 = PASS / FAIL`
- **Action on Finish**: Persist raw evidence and **STOP**.

### STAGE 2: Authentic Qwen + Ornith Workflow
- **Objective**: Prove genuine two-model development workflow in OpenHands without fallbacks, hardcoded code, or direct llama-swap runner shortcuts:
  `Qwen (Planner) -> SwitchLLMTool -> Ornith (Executor) -> Real Tools/Tests -> SwitchLLMTool -> Qwen (Reviewer)`.
- **Actions**:
  1. Create an isolated scratch test workspace.
  2. Dispatch a programming task to Qwen.
  3. Qwen plans and calls `SwitchLLMTool("Ornith-Coding")`.
  4. Ornith writes code and test files, executes real `pytest` via tools (real exit code, stdout/stderr). No fallback code.
  5. *Diagnostic rule*: If Ornith does not transition to tool execution / final action, Stage 2 does **NOT** pass. Diagnose actual profile/runtime/reasoning behavior and correct minimal root cause.
  6. Ornith autonomously calls `SwitchLLMTool("Qwen38_Opus_96K")`.
  7. Qwen inspects raw git diff, changed files, and test output, then issues `PASS`.
- **Gate**: `STAGE_2 = PASS / FAIL`
- **Action on Finish**: Persist raw evidence and **STOP**.

### STAGE 3: Team Presets & Next Integration
- **Objective**: Research supported OpenHands team preset mechanism, configure team modes, and verify alternative pairings without backend bloat.
- **Actions**:
  1. **Research first**: Determine the supported OpenHands mechanism for selecting team presets (inspect OpenHands schema, settings, or agent-profiles).
  2. If supported natively, configure presets; if not, implement a minimal selector/routing layer over existing model profiles without new heavy frameworks.
  3. Verify that switching presets applies correct model profile, instructions, and `SwitchLLMTool` configuration.
  4. Smoke test the `Next + Ornith` pairing (Next plans, Ornith executes).
- **Gate**: `STAGE_3 = PASS / FAIL`
- **Action on Finish**: Persist raw evidence and **STOP**.

### STAGE 4: Automated Heavy Escalation Gate
- **Objective**: Prove automatic escalation to `Next-Normal` strictly on objective physical failure (real exit code != 0), followed by Next diagnosis, Ornith fix, and Qwen review.
- **Actions**:
  1. Run a controlled task with a deterministic concurrency flaw under multi-threaded test.
  2. Cycle 1: Ornith fails -> real pytest exit code != 0 -> Qwen review confirms FAIL (`failure_count = 1`).
  3. Cycle 2: Ornith retry fails -> real pytest exit code != 0 -> Qwen review confirms FAIL (`failure_count = 2`).
  4. Escalation Trigger: Automatic switch to `Next-Normal` with raw failure dossier (code, diff, traceback, objective).
  5. Next produces diagnosis and correction plan.
  6. Switch to Ornith -> Ornith applies fix -> real pytest passes (exit code 0).
  7. Switch to Qwen -> Qwen final review confirms `PASS`.
  8. *Integrity rule*: If Cycle 2 passes, Next is **NOT** invoked.
- **Gate**: `STAGE_4 = PASS / FAIL`
- **Action on Finish**: Persist raw evidence and **STOP**.

### STAGE 5: Production Lifecycle, START/STOP, Ownership & Final Usability
- **Objective**: Validate complete production station ergonomics, clean startup, strict ownership, foreign service preservation, and dynamic VRAM hygiene.
- **Actions**:
  1. Measure VRAM baseline immediately before START (`measured_baseline_vram`).
  2. Start an independent background process to verify non-interference.
  3. Execute `START-OPENHANDS-LOCAL.cmd`:
     - Verify all 5 ports are listening: 8000 (UI), 8080 (llama-swap), 18000 (Agent Server), 18001 (Automation), 18002 (Voice Bridge).
     - Verify Web UI is accessible at `http://localhost:8000`.
     - Verify `session.json` accurately logs owned PIDs.
  4. Execute `STOP-OPENHANDS-LOCAL.cmd`:
     - Unloads models via llama-swap API.
     - Terminates only owned PIDs.
     - Verifies foreign services survive untouched.
     - Verifies ports are cleanly freed.
     - Compares VRAM after STOP against `measured_baseline_vram` with reasonable WDDM/runtime tolerance.
- **Gate**: `STAGE_5 = PASS / FAIL`
- **Action on Finish**: Persist raw evidence and **STOP**.

---

## 5. Post-Station Future Roadmap (Beyond Current Task)

1. **Workstation Daily Use**: Practical daily validation in OpenHands.
2. **Model & MTP Optimization**: Speed tuning, MTP n_max evaluation, and p_min adjustments.
3. **Project Structure Normalization**: Clean directory reorganization.
4. **Mainline Updater**: Automated update scripts for official llama.cpp releases.
5. **Disk Inventory & Cleanup**: Deep cleanup of drives `K:` and `D:`.
6. **Centralized Data Policies**: Centralized logs, temp, archive, trash, and automated retention policies.
