# Strategic Role Evaluation: Qwen3.5-122B-A10B in OpenHands Local

## 1. Quantitative Benchmark Matrix

| Dimension | Qwen3.8-27B Opus (Planner Baseline) | Ornith-1.5-35B (Executor Baseline) | Qwen3.5-122B-A10B (LynnStyle) |
|---|---|---|---|
| **Architecture** | 27B dense | 35B / ~3B active MoE | 122B / ~10B active MoE |
| **Model Size** | 16.5 GB | 19.5 GB | 41.5 GB |
| **GPU Offload** | 100% GPU (999 layers) | 100% GPU (999 layers) | Hybrid (18–21 layers GPU, 28–31 layers CPU) |
| **MTP Decoupling** | MTP n=3, p=0.0 | MTP n=1, p=0.75 | None (MTP not supported) |
| **16K Generation** | ~28.5 tok/s | ~51.2 tok/s | **4.12 – 4.86 tok/s** |
| **96K Follow-up Gen** | ~13.8 tok/s | ~45.9 tok/s | **~4.8 tok/s** |
| **96K Cold TTFT** | ~18.5 s | ~16.2 s | **~700–1200 s** (Bandwidth bound) |
| **Reasoning Depth** | High | Medium-High | **Very High (122B SFT)** |

---

## 2. Strategic Role Analysis

### Role A: Heavy Architect (Primary Autonomous Planner)
- **Verdict**: **REJECTED AS PRIMARY CONTINUOUS PLANNER**
- **Rationale**: An interactive agent cycle with 10–20 tool calling steps would take 30–60 minutes per cycle at ~4.5 tok/s generation speed and slow prompt processing when context exceeds 50K tokens. Qwen27B is 3x faster and Ornith is 10x faster for continuous conversation.

### Role B: Deep Reviewer / Auditor (Offline Verification)
- **Verdict**: **PRIMARY RECOMMENDATION (PERFECT FIT)**
- **Rationale**:
  - The 122B LynnStyle model demonstrates superior reasoning and bug detection on complex concurrency, security, and architectural edge cases compared to 27B and 35B models.
  - In OpenHands, fast models (Ornith or Qwen27B) should execute the code edits, test iterations, and tool loops.
  - When a major milestone, refactoring, or pull request is ready, OpenHands can dispatch the code diff to **Qwen 122B for a dedicated deep audit / sanity review**.
  - Because review happens once per task milestone rather than on every agent turn, latency is acceptable.

### Role C: Escalation Brain (Emergency Debugger)
- **Verdict**: **SECONDARY RECOMMENDATION**
- **Rationale**: If Ornith-1.5 or Qwen3.8-27B get stuck in repeated test failures after 3 attempts, OpenHands can trigger an automated escalation to Qwen 122B to analyze the failure log, formulate a root-cause hypothesis, and hand control back to Ornith.

---

## 3. Integration Roadmap
1. Do not replace existing Qwen27B or Ornith launchers.
2. In the next integration phase, define an optional third profile `qwen122b-auditor` in `llama-swap.yaml` with exclusive swap mode.
