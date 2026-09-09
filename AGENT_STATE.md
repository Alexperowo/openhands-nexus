OBJECTIVE:      OpenHands Nexus — Master Roadmap Execution & Stage 7 Update Hardening
PHASE:          Stage 7 of 9 (Update Hardening & Idempotent Patching)
STATE:          Stages 0–6 are 100% complete and verified. Stage 6 (Team-Full / Agent Runtime) verified PASS: 3-model collaborative chain (Qwen3.8 Opus + Ornith 1.5 + Qwen3-Next 80B), native tool calling on all models (switch_llm, terminal, file_editor), llama-swap VRAM handover under 22 GB budget with clean eviction to 737 MB base, and MTP decoding (Ornith ~63 t/s, Qwen ~21 t/s).
DONE:
  - Stage 0 (Baseline Checkpoint & Inventory): 100% complete.
  - Stage 1 (Working Profiles): 100% complete (7 profiles, server persistence, turn locking).
  - Stage 2 (Remote Control UI): 100% complete (unified card, 3s visibility polling, composer sync).
  - Stage 3 (Reasoning / Thinking): 100% complete (direct/low/med/high, normal/deep, team modes).
  - Stage 4 (Voice + Accessibility + UI Polish): 100% complete (STT, dual TTS, WCAG 2.5.5/2.4.7, UI Sprints 1-4).
  - Stage 5 (Physical Android E2E): 100% complete on Samsung Galaxy Tab S9 Ultra (192.168.0.34:5555).
  - Stage 6 (Team-Full / Agent Runtime): 100% complete.
    - Verified Qwen 3.8 Opus tool calling (`switch_llm` to Ornith in 10.27s).
    - Verified Ornith 1.5 Coder tool calling (`switch_llm` back to Qwen in 2.12s, ~63 t/s generation).
    - Verified clean model eviction and VRAM drops to 737 MiB with zero leaks.
    - Verified swap back to Qwen under 22 GB budget (peak 21,963 MiB).
    - Validated 17 acceptance gates and routing policy (2 normal failures -> Next escalation).
EVIDENCE:
  - Tests & Logs: test_qwen_tool_call.py (PASS), test_ornith_tool_call.py (PASS), test_ornith_lifecycle.py (PASS, 63 t/s), test_swap_to_qwen.py (PASS, VRAM 21,963 MiB).
  - Documentation: OpenHands-Tests/Three-Model-Integration/FINAL-INTEGRATION.md, Docs/ROADMAP.md.
OPEN_ISSUES:    None.
NEXT_ACTION:    Execute Stage 7: Verify Update Hardening procedures, update scripts (OpenHands, Canvas, llama-swap, ik_llama), idempotent patchers, and rollback mechanism.

