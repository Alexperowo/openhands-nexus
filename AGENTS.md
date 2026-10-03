# OpenHands Nexus — Reference Architectural Specification & Workspace Rules

## 1. Core Architecture & Subsystems
- Autonomous local AI engineering workstation on Windows 11 Pro host, architected for cross-environment portability (Windows 10/11, PowerShell, Bash, WSL, and Linux container environments).
- **Untouched Upstream Engine:** Upstream OpenHands core (v1.46.0) remains 100% clean and unmodified. All capabilities operate as sidecars, proxies, profiles, or external supervisors.
- **Microservices & Ports:**
  - `:18005` — Antigravity Bridge Router (Model Catalog, Token Budget Shield, SSE Reasoner)
  - `:8080` — llama-swap Router (dynamic VRAM switching, Dual-GPU slot preservation)
  - `:18002` — Local Voice Bridge (air-gapped GigaAM v3 STT + Supertonic 3 TTS)
  - `:18000` / `:8000` / `:8443` — Legacy OpenHands Engine & Canvas (standby / legacy mode)
- **Role Separation:** Google Antigravity 2.0 operates as the primary Cockpit (Desktop IDE & Touch PWA). Station local models (Qwen 27B, Next 80B, Ornith 35B, Tinfield 177B, Qwen 122B) execute engineering tasks via `:8080` and `:18005`.
- **Management & Control:** Single-click supervisor (`nexus-station.ps1`), emergency safe-switch (`disable-bridge.ps1`), and voice companion (`Services/antigravity-voice/voice_companion.py`).

## 2. Physical Hardware Ceilings (Absolute)
- **System RAM:** Strictly **48 GB** (47.92 GB visible).
- **Dual-GPU VRAM Pool:** Strictly **37.9 GB** ceiling:
  - GPU 0: NVIDIA GeForce RTX 5060 Ti (16 GB VRAM)
  - GPU 1: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM)
- **Workstation Host OS:** Windows 11 Pro with PowerShell 7 (baseline physical workstation).

## 3. Engineering Rigor & Cognitive Discipline
- **Cognitive Sequence:** Grounding (Inspect Disk/Config) $\rightarrow$ Think $\rightarrow$ Plan $\rightarrow$ Collision & Scope Audit $\rightarrow$ Act $\rightarrow$ Verify.
- **Strict Anti-Collision Filters:**
  - **Grounding over Memory:** Never assert from memory or assumptions. Always inspect ground-truth configs, code, and files before drawing conclusions.
  - **Environment Awareness:** No hardcoded single-OS or single-shell assumptions. Dynamic adaptation to active shell (PowerShell, Bash, cmd) and OS (Windows 10/11, Linux, macOS).
  - **Scope Completeness:** Verify the full chain of related files and configs when applying changes (zero desynchronization).
- **Zero Simulation:** Realistic workloads, zero stubs, zero mocks where physical hardware/services exist.
- **Windows Console Signal Safety:** Never invoke `manage_task(Action='kill')` on the Windows host. The language server shares the console process group without isolation; killing a background task via `manage_task` broadcasts `CTRL_C_EVENT`/`SIGINT` to `language_server_windows_x64.exe`, terminating the entire IDE backend and causing "Пользователь остановил агента". Use explicit PowerShell `Stop-Process -Id <pid> -Force` or process-level timeouts instead.
- **Verification Matrix:** Every change must pass targeted tests (`Tests/unit`, `Tests/integration`, `Tests/hardware`).
- **Mechanical Benchmark Integrity:** The agent must NEVER manually transcribe or retype benchmark numbers from terminal output or memory into tables or reports. All benchmark scripts must parse raw metrics directly from process output/JSON and programmatically write the final result files to eliminate human/agent transcription error.
- **Communication:** Natural Russian dialogue as an intelligent engineering peer — concise, clear, zero bureaucracy or filler.

## 4. Post-Install Verification & Recovery State
- **Clean OS Deployment:** The physical system SSD `C:` is prepared for clean installation using master media `K:\Win11_26H2_Custom_Lite_x64.iso` (SHA-256: `38813057CCE09FCAFBAB56AAF802D4076E324617D7A5D26EBDC9BC6ABF049300`).
- **Post-Install Verification Robot:** Upon first boot on the fresh system, execute `powershell -ExecutionPolicy Bypass -File "K:\Project\Verify-PostInstall.ps1"` to programmatically audit all 8 modules (Antigravity Suite, Chrome, GitHub, GPU Limits, AHK/Лупа, UPSSmartView, Disks/Cache, Full Hibernation) and verify all Pass criteria into `K:\Project\POST_INSTALL_VERIFICATION_RESULTS.md`.
- **Pre-Format Backups:** Full `.gemini` folder safely backed up to `D:\BACKUP_C\GEMINI_FULL_BACKUP\`; ComfyUI on `D:\AI\`; conversation logs in `K:\Project\CONVERSATION_HISTORY\`.
