# OpenHands Nexus — Architectural Specification & Workspace Rules

## 1. System Identity & Core Philosophy
- **OpenHands Nexus** is an air-gapped, autonomous local AI engineering workstation on Windows 11.
- **Untouched Upstream Engine:** Upstream OpenHands core remains 100% clean and unmodified. All station capabilities are implemented strictly as non-invasive overlays, reverse proxies, working profile mappings, or idempotent reversible patchers.
- **Role Separation (Testbed vs. Engine):** The user and Antigravity build, supervise, and test the station. The station's *local models* (Tinfield 177B, Qwen 27B, Next 80B, Ornith 35B, Qwen 122B) are the autonomous workers that execute engineering, computer use, and mobile tasks.

## 2. Physical Hardware Ceilings (Strict & Absolute)
- **System RAM:** Strictly **48 GB** (47.92 GB visible) — NOT 64 GB.
- **Dual-GPU VRAM Pool:** Strictly **37.9 GB** ceiling:
  - GPU 0: NVIDIA GeForce RTX 5060 Ti (16 GB VRAM)
  - GPU 1: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM)
- **Host OS:** Windows 11 with PowerShell.

## 3. Subsystem Architecture & Microservices
Nexus orchestrates 5 local microservices:
1. **Port 18000 (OpenHands Core Engine):** Headless agent server executing CodeActAgent with local filesystem and terminal.
2. **Port 8000 (Agent Canvas Web UI):** Desktop web frontend with customized profile/reasoning selectors.
3. **Port 8080 (llama-swap Router):** Dynamic local LLM router managing VRAM swapping, Dual-GPU tensor splitting, 128K context, and reasoning budgets.
4. **Port 8443 (HTTPS LAN PWA Gateway):** Mutual TLS gateway with token authentication for couch operation via tablet.
5. **Port 18002 (Local Voice Bridge):** Air-gapped STT (GigaAM) and TTS (Supertonic) synthesizing executive summaries (`### Резюме`) in <4s.

## 4. Ground Truth & Cognitive Hygiene
- What is configured in `llama-swap/config.yaml` and loaded on disk is real; discarded models (e.g. Mistral) or closed issues (e.g. BUG-01) do not exist.
- Roadmaps are derived strictly from causal physical needs (*what was just built* -> *what physical capability is missing or unverified*), never from grepping obsolete markdown archives.

## 5. Definition of Done & Multi-Platform Verification
No feature or refactoring is complete without empirical proof across the target matrix:
1. **Developer Lens:** Clean non-invasive architecture, zero stubs, strict resource compliance (<=48 GB RAM, <=37.9 GB VRAM).
2. **QA Engineer Lens (Multi-Platform Parity):**
   - **Host Desktop (4K UHD):** Standard mouse/keyboard, DevTools inspection, clean layouts.
   - **Physical Mobile PWA (Samsung Galaxy Tab S9 Ultra, Android 16):** Touch targets >= 48x48 px, virtual keyboard handling, Wi-Fi ADB (`192.168.0.34:5555`).
3. **Execution Reality:** Station capabilities (coding, Computer Use, Android testing) MUST be executed and proven by the station's local models through port 18000, with raw logs and telemetry captured as proof.
