# OpenHands Nexus — Reference Architectural Specification & Workspace Rules

## 1. Core Architecture & Subsystems
- Autonomous local AI engineering workstation on Windows 11 Pro.
- **Untouched Upstream Engine:** Upstream OpenHands core (v1.46.0) remains 100% clean and unmodified. All capabilities operate as sidecars, proxies, profiles, or external supervisors.
- **Microservices & Ports:**
  - `:18000` — OpenHands Core Engine (headless CodeActAgent)
  - `:8000` — Agent Canvas UI (Node/Vite, profile & reasoning injection)
  - `:8080` — llama-swap Router (dynamic VRAM switching, slot preservation)
  - `:8443` — HTTPS LAN Gateway (mTLS, touch PWA, remote operation)
  - `:18002` — Local Voice Bridge (air-gapped GigaAM STT + Supertonic TTS)
- **Role Separation:** Station local models (Tinfield 177B, Qwen 27B, Next 80B, Ornith 35B, Qwen 122B) execute user tasks via port 18000. Supervisor and Antigravity build, inspect, and benchmark.

## 2. Physical Hardware Ceilings (Absolute)
- **System RAM:** Strictly **48 GB** (47.92 GB visible).
- **Dual-GPU VRAM Pool:** Strictly **37.9 GB** ceiling:
  - GPU 0: NVIDIA GeForce RTX 5060 Ti (16 GB VRAM)
  - GPU 1: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM)
- **Host OS:** Windows 11 Pro with PowerShell 7.

## 3. Engineering Rigor & Verification
- **Sequence:** Investigate $\rightarrow$ Think $\rightarrow$ Act.
- **Zero Simulation:** Tests must use realistic workloads (token lengths, context windows, physical telemetry). Zero stubs, zero mocks where physical hardware/services exist.
- **Verification Matrix:** Every change must pass targeted tests (`Tests/unit`, `Tests/integration`, `Tests/hardware`).
