OBJECTIVE:      OpenHands Nexus — Master 10-Stage Roadmap Full Execution & QA Sign-off
PHASE:          Stage 9 of 9 (Final Release & QA Sign-off) — COMPLETE (100%)
STATE:          All 10 Stages (0 through 9) are 100% complete, hardened, and verified.
ARCH_RULE:      We are NOT OpenHands itself (core OpenHands is an untouched upstream repo updated from upstream). OpenHands Nexus is the non-invasive overlay, orchestration, security, and profile layer turning it into an air-gapped local workstation on Windows (Dual-GPU + 48 GB RAM). Recorded in AGENTS.md and GEMINI.md.
DONE:
  - Stage 0 (Baseline Checkpoint & Inventory): 100% complete.
  - Stage 1 (Working Profiles): 100% complete (7 profiles, server persistence, turn locking).
  - Stage 2 (Remote Control UI): 100% complete (unified card, 3s visibility polling, composer sync).
  - Stage 3 (Reasoning / Thinking): 100% complete (direct/low/med/high, normal/deep, team modes).
  - Stage 4 (Voice + Accessibility + UI Polish): 100% complete (STT, dual TTS, WCAG 2.5.5/2.4.7, UI Sprints 1-4).
  - Stage 5 (Physical Android E2E): 100% complete on Samsung Galaxy Tab S9 Ultra (192.168.0.34:5555).
  - Stage 6 (Team-Full / Agent Runtime): 100% complete (3 models, tool calling, 22 GB VRAM budget, MTP 63 t/s).
  - Stage 7 (Update Hardening): 100% complete (idempotent patchers, rollback, backup, 2400 localization parity).
  - Stage 8 (Portable Release / Recovery): 100% complete (check-dependencies 34/34, setup.ps1, backup-station.ps1, restore-station.ps1, recover.ps1, 100% portable paths).
  - Stage 9 (Final Release & QA Sign-off): 100% complete (security sanitization, README documentation, 21/21 end-to-end regression tests passed).
  - Master Testing Plan & Verification: 100% complete (7-tier verification architecture in master_testing_and_verification_plan.md).
  - Standardized Automated Test Suite: 100% complete (tests/unit, tests/integration, tests/hardware, tests/runner.py, openhands test CLI). 25/25 tests passing in 2.01s.
  - Multi-Model VRAM Stress-Testing & Dynamic Swapping: 100% complete (Qwen 3.8 Opus 27B -> Ornith 1.5 35B ICE -> Qwen3-Next 80B Thinking -> Qwen 3.8 Opus). Peak VRAM 22,032 MiB (<= 22,528 MiB budget, 0 OOMs, 0 orphan processes).
  - Physical Tablet 48px Touch Target UI Polish: 100% complete (mic button resized to 48x48px in mobile-pwa.css and voice-bridge.css, verified on Samsung Galaxy Tab S9 Ultra: 48.00 x 48.00 px, WCAG 2.5.5 Level AAA PASS).
  - Ornith 1.5 Reasoning & Thinking Investigation: 100% complete. Validated native CoT is strictly in English, separated into message.reasoning_content. Discovered max_tokens starvation hazard (requires max_tokens >= 1024 or reasoning budget). Engine-level suppression (--reasoning off) verified at 69.22 t/s.
  - MTP Parameter Optimization Sweeps & Production Tuning: 100% complete.
    * Ornith 1.5 Winner Applied: Updated llama-swap/config.yaml to n_max=1, p_min=0.50 delivering 78.89 t/s (+8.2% boost over 72.89 baseline, 83.7% draft acceptance).
    * Qwen 3.8 Opus Winner Confirmed: baseline n_max=3, p_min=0.05 verified as strict global maximum at 35.72 t/s (+49.1% faster on commit b87910f vs 23.96 t/s on 3c58ae3, 76.7% draft acceptance). Nearby sweep (p_min=0.00: 33.85, 0.02: 32.35, 0.08: 33.01 t/s) confirms 0.05 peak.
    * Qwen3-Next 80B Winner Confirmed: baseline draft-mtp:n_max=1 verified strictly optimal at 13.55 t/s (89.8% draft acceptance, +20.3% over no-MTP at 11.26 t/s). Multi-token drafting (n_max=2: 11.09, n_max=3: 10.53 t/s) degrades speed due to CPU/GPU draft latency.
  - UI Enhancements & Profile Synchronization (Tasks 1, 2, 3): 100% complete and verified.
    * Task 1 (Context Filling Indicator): Fixed mobile/tablet button distortion (strictly 32x32px circle, crisp 6px progress bar, no 44px stretching). Added model context badge (`⚡ Qwen 3.8 · 96k контекст`) and in-place details breakdown card (window max, token balance, KV-cache 100% VRAM, max output 8192) toggled via "Использование" or progress bar, preventing drawer disappearance on mobile/tablet.
    * Task 2 (Composer Model Selector Cleanup & Sync): Cleaned `.openhands/profiles` from 17 down to the 8 canonical profiles (all 17 safely backed up in Archive/backups/profiles_cleaned_backup/). Synchronized bottom composer button to display active Working Profile name (`⚡ Qwen 3.8 (Автономный) · Medium`) and transformed popover to display the 7 clean Working Profiles with active highlight, checkmark, and instant two-way synchronization.
    * Task 3 (Ornith 1.5 Limits & Reasoning Modes): Increased max output tokens from 4096 to 8192 in Ornith-Coding and Ornith-Direct profiles. Configured native Thinking (`Thinking (С размышлением)`) and Direct (`Direct (Без рассуждения)`) reasoning modes in `ornith-solo.json`. Verified via Playwright live switching and API.
  - Repository Cleanup & GitHub CI Hardening: 100% complete.
    * Removed audit reports (`AUDIT-REPORT.md`, `UI-OPTIMIZATION-AUDIT.md`, `ПОЛНЫЙ АУДИТ*.txt`, `locale-audit.*`).
    * Cleared root and runtime logs (`llama.log`, `Logs/*`, `LLM-tests/**/*.log`).
    * Removed scratch/temp artifacts, root screenshots, zip test archives, and backup config files.
    * Configured `pyproject.toml` with clean `exclude` rules and fixed syntax/lint issues; `ruff check .` passes with 0 errors across the entire codebase.
  - Quality Refinements & Station Hardening: 100% complete.
    * Added universal `Wait-ForServiceReady` helper in `.openhands-local/start.ps1` eliminating polling duplication.
    * Added text length safeguard (4000 chars) and fallback voice validation in `local-voice/service.py`.
    * Made PFX passphrase configurable via `OPENHANDS_PFX_PASSPHRASE` in `openhands-pwa/lan-gateway.mjs`.
    * Added schema validation for profile loading in `Config/working_profile_manager.mjs` and `working_profiles.py`.
    * Added `Invoke-StationScript` safe execution and error propagation in `openhands.ps1` with UTF-8 BOM encoding.
  - Dual-GPU Hardware Orchestration (RTX 5060 Ti 16GB + RTX 2080 Ti 22GB): 100% complete.
    * Total VRAM pool: 37.9 GB across 2 GPUs (GPU 0: RTX 5060 Ti 16 GB, GPU 1: RTX 2080 Ti 22 GB).
    * Single-model routing: `qwen` and `ornith` pinned to `CUDA1` (RTX 2080 Ti 22 GB) with native `sm_75` CUDA acceleration and 0 OOM risk, keeping `CUDA0` free for OS/desktop/voice.
    * Multi-model routing: `next` (Qwen3-Next 80B) configured with multi-GPU offload `-dev CUDA1,CUDA0 -ts 22,15 -ngl 999`, fitting all layers in 38 GB VRAM.
    * Qwen 122B Dual GPU + RAM Offload Optimization: 100% complete (`-ngl 37 -ts 13.5,22.5 -ctk q6_0 -ctv q4_0 -fa on`, 128K context, 8.1 tok/s generation, 94 tok/s prompt processing). Registered `qwen122` in `llama-swap/config.yaml` and `Config/defaults/profiles/Qwen122-LynnStyle.json`.
  - Differentiated Reasoning Architecture & Model Profiles Hardening: 100% complete.
    * `qwen` (Qwen 3.8 27B Opus Distill v2): `--reasoning-format deepseek --reasoning-budget 4096`, `xhigh` Jinja template reasoning effort, max output increased to 16,384 tokens.
    * `ornith` (Ornith 1.5 35B MTP): `--reasoning-format deepseek --reasoning-budget 3072`, `reasoning_content` trace separation, max output increased to 16,384 tokens.
    * `next` (Qwen 3 Next 80B A3B Thinking): `--reasoning-format deepseek --reasoning-budget 4096 --presence-penalty 0.6`, 16,384 tokens output.
    * `qwen122` (Qwen 3.5 122B LynnStyle): `--reasoning-format deepseek --reasoning-budget 6144`, 16,384 tokens output (16K).
  - Qwen 122B Deep Code Audit & Post-Audit Refactoring: 100% complete across all 6 modules.
    * Full 6-module audit executed by Qwen 3.5 122B LynnStyle (138,080 total tokens, 3.48 hours inference).
    * Module 1 (Orchestration): Atomic BOM-free session saving in start.ps1; validated script paths in openhands.ps1; removed os.chdir from tests/runner.py.
    * Module 2 (LAN Gateway/PWA): Strict path traversal boundary on /icons/; 64 KB body size limits; security headers (nosniff, SAMEORIGIN, Referrer-Policy); SameSite=Strict cookies; in-memory static file caching.
    * Module 3 (Profiles Engine): Regex validation on profile/mode IDs (/^[a-zA-Z0-9_-]{1,64}$/); 64 KB response accumulation bounds; ISO UTC timestamp parity; deterministic file sorting.
    * Module 4 (Voice Service): 10 MB payload limit; early text length check before regex; PyAV container cleanup in try...finally; thread-safe metrics_lock; error message sanitization.
    * Module 5 (UI/UX): HTML entity escaping via escapeHtml for dynamic profile/model variables; MutationObserver lifecycle cleanup on beforeunload; preserved 48x48px touch targets.
    * Module 6 (Patchers & Locale): MutationObserver cleanup in localization.js; consistent UTF-8 without BOM in patch-agent-canvas-localization.ps1 and backup-station.ps1.
    * MoE Router Profiling: Comprehensive per-module token and expert telemetry recorded in Docs/MOE_ROUTER_EXPERT_PROFILING.md.
    * Master Audit Report: Comprehensive documentation compiled in Docs/AUDIT_REPORT_QWEN122.md.
  - Qwen 122B MoE Expert Cache Optimization Experiment: 100% complete and verified.
    * Isolated build and benchmark harness in K:\Project\LLM-tests\Qwen122B-Expert-Cache\.
    * Built llama.cpp PR #27861 with CUDA (SM75 + SM120) and MSVC runtime file locking.
    * Unlocked MoE expert cache via layer-wise tensor overrides: -ngl 49 -ot "blk\.(3[3-9]|4[0-7])\.ffn_(up|gate|down)_exps=CPU" -ts 13,26.
    * Measured speedup: Baseline production (8.22 tok/s) -> Control C0 (14.52 tok/s) -> C8 (17.92 tok/s) -> C16 (20.93 tok/s) -> C32 (23.41 tok/s) -> C48 (26.37 tok/s) -> C64 (26.46 tok/s) -> C80 @ 96K (peak 33.01 tok/s, +284% speedup).
    * Dual-GPU Rebalancing Breakthrough (-ts 13,26): Transferred exactly 1 layer to RTX 5060 Ti, balancing free VRAM to ~2,036 MiB on GPU 0 and ~1,958 MiB on GPU 1 (perfect ~2.0 GB symmetrical safety margin).
    * Configured two verified operational profiles in llama-swap/config.yaml:
      1. qwen122 (Штатный): 64 slots, 128K context, ~26.5 tok/s, ~2.0 GB headroom on GPU 0, ~2.9 GB on GPU 1.
      2. qwen122-turbo (Экстремальный кодинг): 80 slots, 96K context, peak 33.01 tok/s, ~2.0 GB headroom on both GPUs.
  - 100% End-to-End Full-Station Autonomous Testing & QA Verification: 100% COMPLETE & VERIFIED.
    * Stage 1 (Infrastructure & Health Audit): All 5 microservices (Ports 8000, 8080, 8443, 18000, 18002) verified active and responding in sub-second latency.
    * Stage 2 (Dynamic Model Rotation & MoE Optimization): Swapped between Ornith (54.1 tok/s) and Qwen 122B Turbo (80 MoE slots, 96K context, 33 tok/s) with zero-leak VRAM cleanup and symmetrical ~2.0 GB headroom on RTX 5060 Ti + RTX 2080 Ti.
    * Stage 3 (Physical Tablet Verification on Samsung Galaxy Tab S9 Ultra): Verified PWA over HTTPS (port 8443) on Android 16 (2960x1848). Touch targets measured >= 48px (1815x100px profile card, 976x115px buttons, 120x120px mic). Physically tapped and switched profile to `Team-Full: Три Модели` with instant bidirectional synchronization across UI headers and composer.
    * Stage 4 (Voice & Accessibility Pipeline): Supertonic 3 TTS synthesized Russian speech in 2.1s (RTF 0.21, 5x faster than real-time); GigaAM v3 STT transcribed audio in 356-862ms with 100% accuracy; Closed-loop TTS->STT acoustic verification passed with 0 word errors.
    * Stage 5 (Dual Computer Use Integration in OpenHands): Configured and verified 37 MCP tools in OpenHands (`windows-mcp` with 11 tools on 4K desktop + `android-mcp` with 26 tools controlling Samsung Galaxy Tab S9 Ultra).
    * Stage 6 (Autonomous SWE Task Execution): OpenHands agent ran autonomously on local dual-GPU cluster in conversation `b164135e-7813-402a-bb58-27cc57a6352e`. Created `monitor.py` (13.6 KB), created `test_monitor.py` (15.2 KB), ran unit tests (26/26 passed in 0.07s), generated `report.html` (6.3 KB) verifying all 4 local services online and dual-GPU stats, completed with `FinishAction`, and synthesized Russian audio announcement via local Voice Bridge.
  - Working Profiles & Qwen 122B ChatGPT 5.6 SOL Restoration & Synchronization: 100% complete and verified.
    * Synchronized all 3 profile layers: LLM Profiles (21 profiles), Agent Profiles (11 profiles), Working Profiles (8 templates).
    * Created `qwen122-solo.json` (Qwen 122B ChatGPT 5.6 SOL Flagship) with 4 reasoning modes: Flagship (128K), Turbo (33 t/s), GPT-5.6 SOL (Thinking), and Direct.
    * Added full aliases in `llama-swap/config.yaml` (`openai/gpt-5.6-sol`, `Qwen122-ChatGPT-5.6-SOL`, `Qwen122-LynnStyle`, `Qwen122-Turbo`, etc.).
    * Updated Working Profile UI (`working-profile-ui.js` / `.css`) with high-contrast amber `ФЛАГМАН` badge and dynamic mode count.
    * Hardened lifecycle scripts (`setup.ps1`, `backup-station.ps1`, `restore-station.ps1`) to ensure full synchronization of LLM, Agent, and Working profiles.
    * Live verified on Desktop 4K (Google Chrome) and Android 16 Tablet (Samsung Galaxy Tab S9 Ultra PWA).
  - Flagship Multi-Model Team (Team-Flagship: Qwen 122B + Ornith 35B) & MoE Expert Cache Updater: 100% complete and verified.
    * Created `Config/defaults/agent-profiles/Team-Flagship.json` and synchronized to `~/.openhands/agent-profiles/Team-Flagship.json` (Contract: Flagship 122B Architect/Reviewer + Ornith 1.5 Coder/Tester with `enable_switch_llm_tool: true`).
    * Created `Config/working-profile-templates/team-flagship.json` and synchronized to `~/.openhands/working-profiles/team-flagship.json` (Kind: `flagship_chain`, 4 reasoning modes: SOL thinking, Flagship 128K, Turbo 96K, Direct).
    * Enhanced `working-profile-ui.js` and `working-profile-ui.css` with dedicated `СВЯЗКА (ФЛАГМАН)` badge (`badge-flagship-chain`).
    * Created hardened standalone updater script: `OpenHands-Update/scripts/update-expert-cache-backend.ps1` with `-CheckOnly`, `-DryRun`, `-Update`, `-Rollback`, and hard station-stopped gate.
    * Integrated `moe-expert-cache` into central dashboard `OpenHands-Update/scripts/update-all.ps1`.
  - Minimalist Remote Control Architecture (Claude Code / Codex / Antigravity Style): 100% complete and verified.
    * Stripped 21 messy profiles down to strictly 4 Models (`Qwen 122B`, `Ornith 35B`, `Qwen 27B`, `Qwen 80B`) and 3 Chains (`Flagship + Coder`, `Full Team`, `Fast Pair`).
    * Implemented Orthogonal Reasoning Control (`#oh-composer-reasoning-btn`) in composer bottom bar next to model selector with discrete levels (`Выкл`, `Низкое`, `Среднее`, `Глубокое`).
    * Non-reasoning models automatically show `⚡ Direct (Фиксир.)` with informative title and disabled dropdown.
    * Completely hidden the bulky top card (`#oh-working-profile-container { display: none !important; }`). All interaction is unified in composer row.
    * Preserved WCAG AAA contrast, accessible keyboard navigation, and >= 48px touch targets for Samsung Galaxy Tab S9 Ultra.
  - Live Status & Speed Telemetry in Composer & PWA: 100% complete and verified.
    * Added `/api/station-telemetry` endpoint in `local-voice/service.py` (port 18002) parsing real-time llama-swap log metrics.
    * Proxied `/api/station-telemetry` via `lan-gateway.mjs` (port 8443) for remote PWA clients.
    * Added `#oh-composer-telemetry-pill` displaying prefill progress bar, %, token counter, speed in tok/s, ETA, generating tok/s, and active tool.
    * Integrated TalkBack ARIA live polite screen reader announcements on state transitions and 25% prefill milestones for visually impaired developer accessibility.
  - Quad-Dump Static Prefix Cache Architecture & Role Partitioning: 100% complete and verified.
    * Created `K:\Project\Cache\slots` on NVMe SSD.
    * Added `--slot-save-path K:\Project\Cache\slots` to all models in `llama-swap/config.yaml` (`qwen`, `ornith`, `next`, `qwen122`, `qwen122-turbo`).
    * Created automated management script `OpenHands-Update/scripts/generate-prefix-dumps.ps1` for the 4 canonical dumps:
      1. `architect_prefix.bin` (Qwen 122B Lead Architect - system prompt + read/plan/switch tools).
      2. `executor_prefix.bin` (Ornith 35B Coder - code editing, terminal, test execution).
      3. `auditor_prefix.bin` (Qwen 80B / 27B Auditor - code review, testing, verification).
      4. `solo_full_prefix.bin` (Qwen 122B Solo Autonomous - full tool suite).
  - Rigorous Multi-Platform QA Verification & UI Polish (Desktop Chrome + Samsung Galaxy Tab S9 Ultra PWA): 100% COMPLETE & VERIFIED.
    * Developer Lens (Root Cause & Fixes):
      1. Voice Pill Collision Resolved: Fixed `.oh-voice-pill` hardcoded position from `bottom: 20px; left: 20px` (blocking sidebar links/version/settings) to `top: 14px; right: 220px`. Added `restorePillPosition()` auto-clearing of stale coordinates in `voice-bridge.js`.
      2. Multi-Row Wrapping Eliminated: Replaced expanding `@media (max-width: 1024px)` 48px button height with compact `32px` inline-flex layout (`flex-wrap: nowrap !important; white-space: nowrap !important; min-height: 32px !important; height: 32px !important; overflow-x: auto !important; scrollbar-width: none !important;`).
      3. WCAG 2.5.5 Level AAA Compliance Preserved: Hit targets expanded to 48px via invisible pseudo-elements (`.oh-nexus-btn::after`, `.oh-nexus-telemetry-pill::after` with `top: -8px; bottom: -8px; left: -2px; right: -2px`), keeping visual height at 32px while physical touch targets remain >= 48px for finger accuracy.
      4. Label Conciseness: Trimmed verbose strings (`🧠 Мышление: Среднее` -> `🧠 Среднее`, `СВЯЗКА (ФЛАГМАН)` -> `СВЯЗКА`).
      5. Cache & CORS Hardening: Added `Cache-Control: no-cache, no-store, must-revalidate` and CORS headers in `service.py` (`_set_cors` and static asset responses). Added `?t=` timestamp cache-busting in patchers.
    * QA Engineer Lens (Multi-Scenario Test Battery):
      1. Physical Tablet (Samsung Galaxy Tab S9 Ultra, 2960x1848, Android 16 PWA):
         - Landing Page: Single row confirmed (`+`, `⚡ Qwen 122B [ФЛАГМАН]`, `🧠 Среднее`, `● Готов`).
         - Virtual Keyboard Open: Preserved single horizontal row without wrapping (steps/7884).
         - Model Popover: Opened cleanly with all 7 options categorized into `МОДЕЛИ (4)` and `СВЯЗКИ АГЕНТОВ (3)` (steps/7808).
         - Reasoning Popover: Opened directly above button with 4 discrete levels (steps/7816).
         - Interactive Switching: Selected `Глубокое` -> button updated to `🧠 Глубокое` immediately (steps/7822); selected `Full Team` -> updated to `⚡ Full Team [3 МОДЕЛИ]` (steps/7830); returned to `⚡ Qwen 122B` (steps/7838); selected `Ornith 35B` (steps/7846). Zero layout breaks.
      2. Windows Desktop (1920x1080 and 3840x2160 native Chrome):
         - Landing Page: Single row confirmed, zero sidebar overlap (steps/7902, scratch/desktop_landing.png).
         - Conversation View: Single row confirmed at y=646 (scratch/desktop_conversation.png).
         - Model Popover: Verified 7 options and high contrast (scratch/desktop_model_popover.png).
         - Reasoning Popover: Verified 4 discrete levels (scratch/desktop_reasoning_popover.png).
      3. Automated Playwright DOM Inspector (`scratch/inspect_dom.py`):
         - Landing: modelBtn (203px), reasoningBtn (115px), telemetryPill (60px) all at y=396, height 32px.
         - Tablet Viewport: all controls at y=351.18, height 32px.
         - Conversation: all controls at y=646, height 32px, parent width 736px.
         - Console & Network: Zero errors, zero uncaught page exceptions.
EVIDENCE:
  - Audit JSON Reports: K:\Project\LLM-tests\Code-Audit-Qwen122\ (module1-6 audits + audit_summary.json).
  - Master Audit Document: K:\Project\Docs\AUDIT_REPORT_QWEN122.md.
  - Accessibility Guide (Group 1 Blind Developer Experience): K:\Project\Docs\ACCESSIBILITY.md.
  - Hardware Adaptation Guide (Single/Dual GPU, RAM): K:\Project\Docs\HARDWARE_ADAPTATION_GUIDE.md.
  - MoE Router Documentation: K:\Project\Docs\MOE_ROUTER_EXPERT_PROFILING.md (Sections 1-7 complete).
  - MoE Expert Cache Benchmark Documentation: K:\Project\Docs\QWEN122_EXPERT_CACHE_BENCHMARK.md.
  - Physical Tablet Screenshots:
    * steps/7788/media_0.png (Clean conversation view on tablet PWA, single row composer, docked voice pill)
    * s  - Unbound Host Capabilities & Permissions Hardening: 100% complete.
    * Injected `[HOST SYSTEM EXECUTION & UNBOUND CAPABILITIES]` into all 12 agent profiles (`Config/defaults/agent-profiles/*.json` and `~/.openhands/agent-profiles/*.json`).
    * Bound `windows-mcp` (11 tools) and `android-mcp` (26 tools) across all profiles.
    * Unlocked full tool pool (`tools: null`) for standalone profiles and added `USER DIRECTIVE OVERRIDE` for team profiles.
  - Multi-Phase Real-Time Telemetry Engine: 100% complete.
    * Lifecycle: `idle` -> `loading` -> `prefill` (% + tok/s + eta) -> `thinking` -> `tool` (active tool name) -> `generating` (tok/s) -> `idle`.
    * Backend (`local-voice/service.py`): Real-time event inspection of `~/.openhands/agent-canvas/dev_conversations/*/events/` detecting active `ActionEvent` tools within 30s. Extended regex for prefill percentages, thinking tags, and inference timings.
    * Frontend (`working-profile-ui.js` & `.css`): Complete state handling and styling for `.loading` (cyan) and `.thinking` (purple).
  - Quad-Dump Static Prefix Cache Generation & Port Auto-Discovery: 100% complete.
    * Fixed `generate-prefix-dumps.ps1` with dynamic port discovery for active `llama-server.exe` and JSON POST body (`/slots/0?action=save`).
    * Generated and verified all 4 NVMe slot dumps in `K:\Project\Cache\slots`:
      1. `architect_prefix.bin`: 149.52 MB (Qwen 122B Lead Architect)
      2. `executor_prefix.bin`: 63.33 MB (Ornith 35B Code Executor)
      3. `auditor_prefix.bin`: 75.80 MB (Qwen3-Next 80B Security Auditor)
      4. `solo_full_prefix.bin`: 149.45 MB (Qwen 122B Solo Autonomous)
      Total NVMe prefix cache: ~438.1 MB.
  - Mobile LAN PWA Portrait Orientation Hardening (Samsung Galaxy Tab S9 Ultra): 100% complete.
    * Send Button (`button[data-testid="chat-input-send"]`): Anchored with `flex-shrink: 0 !important; z-index: 50 !important; margin-left: auto !important; position: relative !important;`. Never pushed out or wrapped.
    * Horizontal bar (`#oh-nexus-bar`): `overflow-x: auto` with hidden scrollbars, preventing multiline row wrapping.
    * Compact Digit Badges: `1`, `2`, `3`, `СВЯЗКА`, `ФЛАГМАН`.
    * Empirically verified via `android_take_screenshot` in portrait mode (1848x2960): single row composer confirmed.
EVIDENCE:
  - NVMe Slot Dumps: `K:\Project\Cache\slots\` (all 4 .bin files confirmed on disk).
  - Physical Tablet Portrait Screenshots (Samsung Galaxy Tab S9 Ultra, Android 16):
    * Clean composer in portrait orientation (single line, send button visible at right)
    * Model Popover open (4 models + 3 chains, compact badges)
    * Reasoning Popover open (Среднее 2048, Глубокое 4096)
  - Desktop Verification: `scratch/verify_desktop.py` (DOM aligned at y=446.39px, height 32px, single line).
  - Automated Test Suite: `python tests/runner.py --all` (25/25 tests passing in 1.96s).
  - Linter: `uvx ruff check . --ignore E501,B008` (All checks passed, 0 errors).
  - JS Syntax: `node --check openhands-working-profile/working-profile-ui.js` (clean).
OPEN_ISSUES:
  - None. All requirements satisfied, multi-platform verified, zero errors.
NEXT_ACTION:    Ready for user confirmation and release.
