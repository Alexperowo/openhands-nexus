# OpenHands Nexus — Architectural Concept & Workspace Rules

## 1. Core Architectural Identity
- **We are NOT OpenHands itself.** OpenHands is an external upstream open-source project.
- **Untouched Upstream Engine:** The core OpenHands codebase is treated as an external dependency. It remains completely unmodified in its original repository structure and is updated directly via upstream git pulls.
- **Our Identity:** Our codebase is **OpenHands Nexus** — the non-invasive, autonomous overlay, integration, and orchestration layer that turns OpenHands into an air-gapped, local AI engineering workstation on Windows.

## 2. Hardware Specification & Environment Constraints
- **System RAM:** Strictly **48 GB** (47.92 GB visible), NOT 64 GB.
- **Dual GPU Setup:**
  - GPU 0: NVIDIA GeForce RTX 5060 Ti (16 GB VRAM)
  - GPU 1: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM)
  - Combined VRAM Pool: ~37.9 GB
- **Operating System:** Windows 10/11 with PowerShell.

## 3. Subsystem Architecture of the Nexus Overlay
The custom overlay provides distinct subsystems around the untouched OpenHands core:
1. **Station Orchestration & Process Lifecycle:**
   - Supervises 5 local microservices:
     * Port 18000: OpenHands Core Engine
     * Port 8000: Agent Canvas Web UI
     * Port 8080: llama-swap LLM Router
     * Port 8443: HTTPS LAN Gateway (PWA)
     * Port 18002: Local Neural Voice Bridge (GigaAM / TTS)
   - Manages process trees via WMI/CIM, session tracking (session.json), port readiness polling, and graceful termination (openhands.ps1, start.ps1, runner.py).
2. **Local LLM Dynamic Routing (llama-swap + ik_llama):**
   - Dynamic model swapping with zero-leak VRAM allocation (budget <= 37.9 GB).
   - Dual-GPU tensor splitting (-dev CUDA0,CUDA1 -ts ...), 128K context window, asymmetric KV caching (q6_0/q4_0), MTP acceleration, and hardware reasoning budgets (--reasoning-budget).
3. **LAN Gateway & PWA Security Layer (lan-gateway.mjs):**
   - Mutual TLS termination (local Root CA + Leaf SAN certificate), token-based authentication, WebSocket proxying.
   - PWA delivery for remote control via mobile devices and tablets (Samsung Galaxy Tab S9 Ultra).
4. **Working Profiles Dual-Stack Engine:**
   - Synchronizes model profiles between Node.js (working_profile_manager.mjs) and Python (working_profiles.py).
   - Manages reasoning modes (Thinking vs Direct), prompt template kwargs, and token generation ceilings (16K window: max_output_tokens: 16384).
5. **Local Neural Voice Pipeline (local-voice/service.py):**
   - Air-gapped STT (GigaAM) and TTS running locally on port 18002 with strict memory/buffer management.
6. **Non-Destructive Patchers & Localization (OpenHands-Update/scripts/):**
   - Idempotent scripts that inject UI enhancements (touch targets, model selectors, indicators) and full 2400-key Russian localization into the frontend bundle.
   - Must remain 100% reversible with automated backup and restore so that upstream OpenHands can be updated cleanly at any time.

## 4. Development & Refactoring Principles
- Never modify upstream OpenHands core files directly.
- All station features must be implemented as non-invasive wrappers, reverse proxies, profile mappings, or idempotent patchers.
- Any refactoring must preserve upstream update compatibility and backup/rollback capability.
- Memory budgets must strictly respect the 48 GB RAM and 37.9 GB VRAM ceiling.

## 5. Definition of Done, QA Verification Discipline & Critical Thinking
**Mandatory and Non-Negotiable Across the Entire Project:**
No feature, refactoring, bugfix, or UI modification is ever considered "Ready" or "Complete" without empirical multi-platform proof. Never declare completion based on assumption, plan, compilation, or a simple HTTP 200 / service startup. Every agent and contributor working in this repository must apply the **Three Engineering Lenses**:

1. **Developer Lens (Root Cause & Architectural Cleanliness):**
   - Non-invasive overlay architecture: never patch upstream OpenHands core files directly.
   - Zero cosmetic workarounds: fix problems at their root cause.
   - Adherence to standards: WCAG 2.5.5 Level AAA touch targets ($\ge 48\times48\text{ px}$), clean CSS layouts without overlapping or brittle absolute positions, strict typing/linting, zero unhandled exceptions, and zero console errors.
   - Resource ceilings: respect 48 GB RAM and 37.9 GB Dual-GPU VRAM limits without compromise.

2. **QA Engineer Lens (Multi-Platform & Scenario Matrix Testing):**
   - **Cross-Platform Parity:** Every change touching UI, gateway, routing, or agent workflows MUST be tested and verified on BOTH:
     * **Desktop Chrome / Edge** (Standard desktop viewports, mouse/keyboard interactions, DevTools inspection).
     * **Physical Mobile LAN PWA** (Samsung Galaxy Tab S9 Ultra / Android / mobile touch screens).
   - **Stress & Edge-Case Testing:**
     * Viewport resizes, landscape vs portrait orientation transitions.
     * On-screen virtual keyboard appearance (preventing composer or popover collapse/overlap).
     * Popover menu containment and viewport collision detection.
     * Real-time network transitions (WebSockets reconnect, polling timeouts, offline handling).
     * Rapid repeated taps, simultaneous multi-touch, and screen reader / accessibility focus traversals.

3. **Critical Thinking Lens (Raw Evidence Over Claims):**
   - Scrutinize raw telemetry, log traces, and screenshots before making assertions.
   - A service running on a port is NOT proof of functional end-to-end correctness.
   - If an edge case or platform scenario has not been verified empirically with raw logs or visual artifacts, it must be explicitly reported as `UNVERIFIED` or `PARTIAL`, NEVER as `Complete`.
   - Never rationalize or explain away contradictory evidence; resolve it.
