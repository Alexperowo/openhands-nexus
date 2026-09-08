import os, json, datetime

evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6a_evidence"
root = r"K:\Project"

# 1. CREATE PROPOSED STRUCTURE
proposed_structure_data = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "canonical_root": "K:\\Project",
    "design_principles": [
        "Preserve existing working production paths to avoid breaking active services",
        "Minimize disruption: do NOT move active production directories during Stage 6A",
        "K: is the single canonical disk for all active production models",
        "Centralize logs, archives, documentation, and loose test scripts into logical buckets"
    ],
    "structure_specification": {
        "Models": {
            "path": "K:\\Project\\Models",
            "role": "Canonical repository for GGUF weights, draft models, and vision projectors",
            "active_subdirectories": {
                "Qwen3.8": "Target canonical home for Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf and mmproj-f16.gguf (already copied & verified)",
                "Ornith": "Recommended subdirectory for Ornith-1.5-35B-MTP-19G-ICE.gguf and mmproj (can remain in Models root or nest in 6B)",
                "Qwen3-Next": "Recommended subdirectory for Qwen3-Next-80B and MTP draft model"
            },
            "status": "EXISTS_ACTIVE"
        },
        "Backends": {
            "path": "K:\\Project\\Backends",
            "role": "Central container for inference engines and routers (virtual / target canonical grouping)",
            "mapped_existing_paths": {
                "ik_llama": "K:\\Project\\ik_llama (preserves active working path for Qwen and Ornith)",
                "llama-mainline": "K:\\Project\\llama-mainline (preserves active working path for Qwen3-Next)",
                "llama-swap": "K:\\Project\\llama-swap (preserves active working path for port 8080 model router)",
                "transcribe-build-shared": "K:\\Project\\transcribe-build-shared (preserves active working path for local-voice STT)"
            },
            "recommendation": "Retain top-level paths during current baseline to avoid breaking scripts; optionally symlink or nest in later stages"
        },
        "Config": {
            "path": "K:\\Project\\Config",
            "role": "Centralized configuration references and agent profiles",
            "mapped_existing_paths": {
                ".openhands-local": "Launcher scripts and configuration",
                "llama-swap/config.yaml": "Active 3-model routing configuration"
            }
        },
        "Scripts": {
            "path": "K:\\Project\\Scripts",
            "role": "Central repository for operational, setup, and maintenance scripts",
            "mapped_existing_paths": {
                "root_cmd": "START, STOP, RESTART, DIAGNOSTICS scripts remain in root for 1-click accessibility",
                "OpenHands-Update": "Update and rollback scripts maintain their dedicated subsystem"
            }
        },
        "Runtime": {
            "path": "K:\\Project\\Runtime",
            "role": "Active working directories and runtime state (PID files, session locks)",
            "mapped_existing_paths": {
                ".openhands-local": "Stores runtime PID and session info",
                "llama-swap/session.json": "Active swap session tracking"
            }
        },
        "Tests": {
            "path": "K:\\Project\\Tests",
            "role": "Consolidated test suites, benchmarks, and verification evidence",
            "mapped_existing_paths": {
                "OpenHands-Tests": "Primary active test station and multi-stage verification evidence",
                "LLM-tests": "Historical model benchmarking and fine-tuning suites",
                "AgentCanvas-Test": "Agent Canvas smoke testing workspace",
                "legacy_root": "Target directory for 31 standalone test scripts currently in root"
            }
        },
        "Logs": {
            "path": "K:\\Project\\Logs",
            "role": "Unified log collection directory for all background services",
            "subdirectories": [
                "K:\\Project\\Logs\\openhands",
                "K:\\Project\\Logs\\llama-server",
                "K:\\Project\\Logs\\llama-swap",
                "K:\\Project\\Logs\\voice-bridge"
            ],
            "status": "TARGET_EMPTY_DIR_CREATED"
        },
        "Temp": {
            "path": "K:\\Project\\Temp",
            "role": "Scratch runtime storage and disposable test outputs",
            "status": "TARGET_EMPTY_DIR_CREATED"
        },
        "Docs": {
            "path": "K:\\Project\\Docs",
            "role": "Project documentation, help manuals, and reference architecture diagrams",
            "status": "TARGET_EMPTY_DIR_CREATED"
        },
        "Archive": {
            "path": "K:\\Project\\Archive",
            "role": "Cold storage for obsolete builds, test archives, backups, and deprecated files",
            "subdirectories": [
                "K:\\Project\\Archive\\backups",
                "K:\\Project\\Archive\\zip_archives",
                "K:\\Project\\Archive\\deprecated_builds"
            ],
            "status": "TARGET_EMPTY_DIR_CREATED"
        }
    }
}

with open(os.path.join(evidence_dir, "proposed_structure.json"), "w", encoding="utf-8") as f:
    json.dump(proposed_structure_data, f, indent=2, ensure_ascii=False)
print("proposed_structure.json created.")

# 2. CREATE MIGRATION MAP
migration_items = []

# Scattered Logs
migration_items.append({
    "current_path": "K:\\Project\\llama.log",
    "proposed_path": "K:\\Project\\Logs\\llama.log",
    "category": "LOG",
    "size_bytes": 3358,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Scattered root log file. Unreferenced by any production script."
})
migration_items.append({
    "current_path": "K:\\Project\\Models\\smoke_test.err.log",
    "proposed_path": "K:\\Project\\Logs\\smoke_test.err.log",
    "category": "LOG",
    "size_bytes": 14512,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Misplaced stderr test log in Models directory."
})
migration_items.append({
    "current_path": "K:\\Project\\Models\\smoke_test.out.log",
    "proposed_path": "K:\\Project\\Logs\\smoke_test.out.log",
    "category": "LOG",
    "size_bytes": 2864,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Misplaced stdout test log in Models directory."
})
migration_items.append({
    "current_path": "K:\\Project\\llama-swap\\llama.log",
    "proposed_path": "K:\\Project\\Logs\\llama-swap\\llama.log",
    "category": "LOG",
    "size_bytes": 738,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Local swap log. Production logs configured in start.ps1 to .openhands-local\\logs."
})

# Scattered Archives
migration_items.append({
    "current_path": "K:\\Project\\Three-Model-Integration-Full-Archive.zip",
    "proposed_path": "K:\\Project\\Archive\\zip_archives\\Three-Model-Integration-Full-Archive.zip",
    "category": "ARCHIVE",
    "size_bytes": 11931770,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Historical test evidence zip archive."
})
migration_items.append({
    "current_path": "K:\\Project\\Three-Model-Integration-Supplemental-Evidence.zip",
    "proposed_path": "K:\\Project\\Archive\\zip_archives\\Three-Model-Integration-Supplemental-Evidence.zip",
    "category": "ARCHIVE",
    "size_bytes": 12745550,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Historical test evidence zip archive."
})

# Backup Files
migration_items.append({
    "current_path": "K:\\Project\\.openhands-local\\start.ps1.bak",
    "proposed_path": "K:\\Project\\Archive\\backups\\start.ps1.bak",
    "category": "BACKUP",
    "size_bytes": 13570,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Previous backup of start.ps1."
})
migration_items.append({
    "current_path": "K:\\Project\\.openhands-local\\stop.ps1.bak",
    "proposed_path": "K:\\Project\\Archive\\backups\\stop.ps1.bak",
    "category": "BACKUP",
    "size_bytes": 7935,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Previous backup of stop.ps1."
})
migration_items.append({
    "current_path": "K:\\Project\\llama-swap\\config.yaml.backup.20260905_105239",
    "proposed_path": "K:\\Project\\Archive\\backups\\config.yaml.backup.20260905_105239",
    "category": "BACKUP",
    "size_bytes": 1006,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Previous backup of config.yaml."
})

# Documentation / Reference files in root
migration_items.append({
    "current_path": "K:\\Project\\ik_llama_help.txt",
    "proposed_path": "K:\\Project\\Docs\\ik_llama_help.txt",
    "category": "DOCUMENTATION",
    "size_bytes": 75163,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Reference command line help output for ik_llama."
})
migration_items.append({
    "current_path": "K:\\Project\\final_about_tablet.png",
    "proposed_path": "K:\\Project\\Docs\\final_about_tablet.png",
    "category": "DOCUMENTATION",
    "size_bytes": 319896,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "UI reference screenshot."
})

# Temp and Test results in root / fixtures
migration_items.append({
    "current_path": "K:\\Project\\all_modes_results.json",
    "proposed_path": "K:\\Project\\Tests\\legacy_root\\all_modes_results.json",
    "category": "TEST_ARTIFACT",
    "size_bytes": 5014,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Standalone test execution results."
})
migration_items.append({
    "current_path": "K:\\Project\\AgentCanvas-Test\\screenshot_safe.png",
    "proposed_path": "K:\\Project\\Temp\\screenshot_safe.png",
    "category": "TEMP",
    "size_bytes": 28050,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Smoke test capture artifact in test workspace."
})
migration_items.append({
    "current_path": "K:\\Project\\AgentCanvas-Test\\test.txt",
    "proposed_path": "K:\\Project\\Temp\\test.txt",
    "category": "TEMP",
    "size_bytes": 44,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Smoke test text fixture."
})
migration_items.append({
    "current_path": "K:\\Project\\AgentCanvas-Test\\test.ps1",
    "proposed_path": "K:\\Project\\Temp\\test.ps1",
    "category": "TEMP",
    "size_bytes": 68,
    "action_type": "RELOCATE_FILE",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Smoke test script fixture."
})

# Root legacy test python scripts (31 files)
root_py_test_scripts = [
    "benchmark_voice_full.py", "inspect_conv_req.py", "test_all_modes.py",
    "test_barge_in.py", "test_bgt.py", "test_budget.py", "test_comb.py",
    "test_combined_memory.py", "test_compare.py", "test_direct2.py",
    "test_direct_deepseek.py", "test_direct_inst.py", "test_direct_prompt.py",
    "test_exact.py", "test_futo_stt.py", "test_jinja_render.py", "test_litellm.py",
    "test_litellm_both.py", "test_litellm_budget.py", "test_litellm_direct.py",
    "test_off_modes.py", "test_persistent_stt.py", "test_raw_prompt.py",
    "test_reasoning_syntax.py", "test_rf.py", "test_save_profile.py",
    "test_single_profile.py", "test_val.py", "test_voice_bridge_stt.py",
    "test_voice_bridge_tts.py"
]

for s in root_py_test_scripts:
    fp = os.path.join(root, s)
    sz = os.path.getsize(fp) if os.path.exists(fp) else 0
    migration_items.append({
        "current_path": fp,
        "proposed_path": f"K:\\Project\\Tests\\legacy_root\\{s}",
        "category": "TEST_SCRIPT",
        "size_bytes": sz,
        "action_type": "RELOCATE_FILE",
        "status": "PLANNED_STAGE_6B",
        "safety_note": "Standalone development/test script not referenced by production runtime."
    })

# Duplicate candidates to clean or archive in Stage 6B
migration_items.append({
    "current_path": "K:\\Project\\llama.cpp",
    "proposed_path": "K:\\Project\\Archive\\deprecated_builds\\llama.cpp",
    "category": "DUPLICATE_BACKEND",
    "action_type": "RELOCATE_OR_REMOVE_DIRECTORY",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Duplicate of llama-mainline\\b10816. Unreferenced."
})
migration_items.append({
    "current_path": "K:\\Project\\transcribe-build",
    "proposed_path": "K:\\Project\\Archive\\deprecated_builds\\transcribe-build",
    "category": "DUPLICATE_BUILD",
    "action_type": "RELOCATE_OR_REMOVE_DIRECTORY",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Static build directory. Active service links to transcribe-build-shared."
})
migration_items.append({
    "current_path": "K:\\Project\\OpenHands",
    "proposed_path": "NONE (REMOVE_EMPTY_DIR)",
    "category": "EMPTY_DIRECTORY",
    "action_type": "REMOVE_EMPTY_DIRECTORY",
    "status": "PLANNED_STAGE_6B",
    "safety_note": "Completely empty directory remnant (0 bytes)."
})

# Qwen 3.8 Model Transition
migration_items.append({
    "current_path": "D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
    "proposed_path": "K:\\Project\\Models\\Qwen3.8\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
    "category": "MODEL",
    "size_bytes": 16810714688,
    "action_type": "COPIED_AND_VERIFIED",
    "status": "COPIED_IN_STAGE_6A_CONFIG_SWITCH_PENDING_STAGE_6B",
    "safety_note": "File copied to K: and SHA256 verified. Source on D: preserved untouched. Production config.yaml still points to D: until Stage 6B."
})
migration_items.append({
    "current_path": "D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf",
    "proposed_path": "K:\\Project\\Models\\Qwen3.8\\Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf",
    "category": "MODEL",
    "size_bytes": 927607296,
    "action_type": "COPIED_AND_VERIFIED",
    "status": "COPIED_IN_STAGE_6A_CONFIG_SWITCH_PENDING_STAGE_6B",
    "safety_note": "Vision companion copied to K: and SHA256 verified. Source on D: preserved untouched."
})

migration_map_data = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "stage": "STAGE_6A",
    "rules": {
        "files_moved_in_6a": "NONE",
        "files_deleted_in_6a": "NONE",
        "production_config_changed": "NO",
        "qwen38_source_preserved": "YES"
    },
    "summary_counts": {
        "total_migration_entries": len(migration_items),
        "logs_to_relocate_count": sum(1 for m in migration_items if m["category"] == "LOG"),
        "temp_items_to_relocate_count": sum(1 for m in migration_items if m["category"] == "TEMP"),
        "duplicate_candidates_count": 6,
        "obsolete_candidates_count": sum(1 for m in migration_items if m["category"] in ["TEST_SCRIPT", "TEST_ARTIFACT", "ARCHIVE", "EMPTY_DIRECTORY"])
    },
    "migration_entries": migration_items
}

with open(os.path.join(evidence_dir, "migration_map.json"), "w", encoding="utf-8") as f:
    json.dump(migration_map_data, f, indent=2, ensure_ascii=False)
print("migration_map.json created.")
