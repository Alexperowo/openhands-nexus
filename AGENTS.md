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
   - Manages process trees via WMI/CIM, session tracking (session.json), port readiness polling, and graceful termination (openhands.ps1, start.ps1, 
unner.py).
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
