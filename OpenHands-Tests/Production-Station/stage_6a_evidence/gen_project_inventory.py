import os, json, hashlib, datetime

evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6a_evidence"
root = r"K:\Project"

# 1. GENERATE project_inventory.json
print("Building project_inventory.json...")

top_dirs_info = {
    ".git": {
        "category": "CONFIG",
        "subcategory": "SCM",
        "description": "Git repository metadata for K:\\Project"
    },
    ".openhands-local": {
        "category": "PRODUCTION",
        "subcategory": "SCRIPTS_AND_CONFIG",
        "description": "OpenHands local launcher scripts (start.ps1, stop.ps1, diagnostics.ps1) and runtime logs"
    },
    "AgentCanvas-Test": {
        "category": "TEST",
        "subcategory": "SMOKE_FIXTURE",
        "description": "Test fixture directory used during OpenHands Stage 5 smoke tests"
    },
    "LLM-tests": {
        "category": "TEST",
        "subcategory": "BENCHMARKS_AND_TUNING",
        "description": "Extensive model benchmarking, MTP fine-tuning, and prompt testing suite"
    },
    "Models": {
        "category": "MODEL",
        "subcategory": "CANONICAL_MODEL_STORAGE",
        "description": "Primary storage directory for GGUF model weights, vision projectors, and companion files"
    },
    "OpenHands": {
        "category": "OBSOLETE_CANDIDATE",
        "subcategory": "EMPTY_DIRECTORY",
        "description": "Empty directory remnant from earlier setup (0 files, 0 bytes)"
    },
    "OpenHands-Tests": {
        "category": "TEST",
        "subcategory": "EVIDENCE_AND_INTEGRATION_TESTS",
        "description": "Test harness, integration tests, and production station verification stages (Stages 1-6A)"
    },
    "OpenHands-Update": {
        "category": "SCRIPT",
        "subcategory": "MAINTENANCE_AND_UPDATE",
        "description": "Updater and rollback scripts for OpenHands and ik_llama backends"
    },
    "android-mcp": {
        "category": "PRODUCTION",
        "subcategory": "MCP_EXTENSION",
        "description": "Model Context Protocol server for Android automation and ADB integration"
    },
    "ik_llama": {
        "category": "BACKEND",
        "subcategory": "PRODUCTION_INFERENCE_ENGINE",
        "description": "Custom high-performance llama.cpp fork with built-in MTP spec decoding for Qwen 3.8 and Ornith"
    },
    "ksenia-android": {
        "category": "PRODUCTION",
        "subcategory": "VOICE_CLIENT",
        "description": "Android client application for voice assistant integration"
    },
    "llama-mainline": {
        "category": "BACKEND",
        "subcategory": "PRODUCTION_INFERENCE_ENGINE",
        "description": "Mainline llama.cpp build (b10816) running Qwen3-Next-80B with external MTP draft model"
    },
    "llama-swap": {
        "category": "BACKEND",
        "subcategory": "MODEL_SWITCHER_ROUTER",
        "description": "Dynamic model switcher / proxy server routing requests to backend instances on demand"
    },
    "llama.cpp": {
        "category": "OBSOLETE_CANDIDATE",
        "subcategory": "DUPLICATE_BACKEND",
        "description": "Unversioned duplicate build of llama-mainline (55 files matching b10816, not referenced by production config)"
    },
    "local-voice": {
        "category": "PRODUCTION",
        "subcategory": "VOICE_BRIDGE_SERVICE",
        "description": "Local voice bridge service (STT via FUTO transcribe.cpp, TTS via Silero, port 18002)"
    },
    "openhands-localization": {
        "category": "PRODUCTION",
        "subcategory": "LOCALIZATION_EXTENSION",
        "description": "Russian localization patches and UI translations for Agent Canvas"
    },
    "transcribe-build": {
        "category": "OBSOLETE_CANDIDATE",
        "subcategory": "STATIC_BUILD_ARTIFACT",
        "description": "Static build directory for transcribe.cpp (unreferenced by production services)"
    },
    "transcribe-build-shared": {
        "category": "BACKEND",
        "subcategory": "PRODUCTION_STT_RUNTIME",
        "description": "Shared library build directory containing transcribe.dll required by local-voice service"
    }
}

top_dirs = []
for dname in sorted(os.listdir(root)):
    dpath = os.path.join(root, dname)
    if os.path.isdir(dpath):
        fcount = 0
        tsize = 0
        try:
            for dp, _, fns in os.walk(dpath):
                fcount += len(fns)
                for f in fns:
                    try:
                        tsize += os.path.getsize(os.path.join(dp, f))
                    except:
                        pass
        except:
            pass
        meta = top_dirs_info.get(dname, {"category": "UNKNOWN", "subcategory": "UNKNOWN", "description": "Unclassified directory"})
        top_dirs.append({
            "name": dname,
            "path": dpath,
            "category": meta["category"],
            "subcategory": meta["subcategory"],
            "description": meta["description"],
            "file_count": fcount,
            "total_size_bytes": tsize
        })

top_files = []
for fname in sorted(os.listdir(root)):
    fpath = os.path.join(root, fname)
    if os.path.isfile(fpath):
        sz = os.path.getsize(fpath)
        cat = "UNKNOWN"
        desc = ""
        if fname in ["START-OPENHANDS-LOCAL.cmd", "STOP-OPENHANDS-LOCAL.cmd", "RESTART-OPENHANDS-LOCAL.cmd", "DIAGNOSTICS-OPENHANDS-LOCAL.cmd"]:
            cat = "PRODUCTION"
            desc = "Production launcher / control script"
        elif fname.endswith(".zip"):
            cat = "ARCHIVE"
            desc = "Packaged historical test archive"
        elif fname.endswith(".log"):
            cat = "LOG"
            desc = "Loose log file in root"
        elif fname.endswith(".json"):
            cat = "TEST"
            desc = "Test result artifact"
        elif fname.endswith((".txt", ".png")):
            cat = "DOCUMENTATION"
            desc = "Documentation or reference media"
        elif fname.startswith("test_") or fname in ["benchmark_voice_full.py", "inspect_conv_req.py"]:
            cat = "TEST"
            desc = "Standalone / legacy test script in root"
        elif fname in ["setup_openhands_profiles.py", "verify_openhands_profiles.py"]:
            cat = "SCRIPT"
            desc = "One-off profile configuration and verification utility"
        
        top_files.append({
            "name": fname,
            "path": fpath,
            "category": cat,
            "description": desc,
            "size_bytes": sz
        })

project_inventory = {
    "root_path": root,
    "inventory_timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "summary": {
        "total_top_level_directories": len(top_dirs),
        "total_top_level_files": len(top_files),
        "total_storage_bytes_k_project": sum(d["total_size_bytes"] for d in top_dirs) + sum(f["size_bytes"] for f in top_files)
    },
    "top_level_directories": top_dirs,
    "top_level_files": top_files,
    "specialized_subsystem_findings": {
        "models": {
            "canonical_directory": "K:\\Project\\Models",
            "active_models": [
                {"name": "Qwen 3.8", "current_production_ref": "D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf", "copied_canonical_path": "K:\\Project\\Models\\Qwen3.8\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"},
                {"name": "Ornith 1.5", "current_production_ref": "K:\\Project\\Models\\Ornith-1.5-35B-MTP-19G-ICE.gguf"},
                {"name": "Qwen3-Next", "current_production_ref": "K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf", "draft_model": "K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf"}
            ],
            "misplaced_files_in_models": [
                "K:\\Project\\Models\\smoke_test.err.log",
                "K:\\Project\\Models\\smoke_test.out.log"
            ]
        },
        "backends": {
            "ik_llama": "K:\\Project\\ik_llama\\bin\\llama-server.exe (Production: Qwen, Ornith)",
            "llama_mainline": "K:\\Project\\llama-mainline\\b10816\\llama-server.exe (Production: Qwen3-Next)",
            "llama_swap": "K:\\Project\\llama-swap\\bin\\llama-swap.exe (Production Router on port 8080)",
            "transcribe_shared": "K:\\Project\\transcribe-build-shared\\bin\\Release\\transcribe.dll (Production STT backend)"
        },
        "start_stop_scripts": [
            "K:\\Project\\START-OPENHANDS-LOCAL.cmd",
            "K:\\Project\\STOP-OPENHANDS-LOCAL.cmd",
            "K:\\Project\\RESTART-OPENHANDS-LOCAL.cmd",
            "K:\\Project\\DIAGNOSTICS-OPENHANDS-LOCAL.cmd",
            "K:\\Project\\.openhands-local\\start.ps1",
            "K:\\Project\\.openhands-local\\stop.ps1",
            "K:\\Project\\.openhands-local\\diagnostics.ps1"
        ],
        "backup_files": [
            "K:\\Project\\.openhands-local\\start.ps1.bak",
            "K:\\Project\\.openhands-local\\stop.ps1.bak",
            "K:\\Project\\llama-swap\\config.yaml.backup.20260905_105239"
        ],
        "obsolete_and_duplicate_candidates": [
            "K:\\Project\\llama.cpp",
            "K:\\Project\\OpenHands",
            "K:\\Project\\transcribe-build"
        ]
    }
}

with open(os.path.join(evidence_dir, "project_inventory.json"), "w", encoding="utf-8") as f:
    json.dump(project_inventory, f, indent=2, ensure_ascii=False)
print("project_inventory.json created.")
