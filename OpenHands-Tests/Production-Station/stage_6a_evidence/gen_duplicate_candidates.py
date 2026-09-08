import os, json, hashlib, datetime

evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6a_evidence"
root = r"K:\Project"

def get_sha256(filepath):
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(1024*1024):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        return str(e)

print("Computing selective hashes...")
hash_start_ps1 = get_sha256(r"K:\Project\.openhands-local\start.ps1")
hash_start_bak = get_sha256(r"K:\Project\.openhands-local\start.ps1.bak")
hash_stop_ps1 = get_sha256(r"K:\Project\.openhands-local\stop.ps1")
hash_stop_bak = get_sha256(r"K:\Project\.openhands-local\stop.ps1.bak")
hash_root_llama_log = get_sha256(r"K:\Project\llama.log")

duplicate_candidates_data = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "scope": "K:\\Project",
    "categories": {
        "SAFE_DUPLICATE_CANDIDATE": [
            {
                "item": "K:\\Project\\llama.cpp",
                "type": "DIRECTORY",
                "file_count": 55,
                "total_size_bytes": 1166160896,
                "comparison_target": "K:\\Project\\llama-mainline\\b10816",
                "notes": "Older untagged build of llama-mainline. 46 files match in size; missing release metadata files. Not referenced by config.yaml or any launcher.",
                "action_recommendation": "SAFE_TO_ARCHIVE_OR_REMOVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\transcribe-build",
                "type": "DIRECTORY",
                "file_count": 518,
                "total_size_bytes": 86170000,
                "comparison_target": "K:\\Project\\transcribe-build-shared",
                "notes": "Static build directory for transcribe.cpp. Production local-voice service specifically links to transcribe-build-shared\\bin\\Release\\transcribe.dll.",
                "action_recommendation": "SAFE_TO_ARCHIVE_OR_REMOVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\.openhands-local\\start.ps1.bak",
                "type": "FILE",
                "size_bytes": 13570,
                "comparison_target": "K:\\Project\\.openhands-local\\start.ps1 (13072 bytes)",
                "sha256": hash_start_bak,
                "target_sha256": hash_start_ps1,
                "notes": "Pre-modification backup of start.ps1 created during previous scripting passes.",
                "action_recommendation": "MOVE_TO_ARCHIVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\.openhands-local\\stop.ps1.bak",
                "type": "FILE",
                "size_bytes": 7935,
                "comparison_target": "K:\\Project\\.openhands-local\\stop.ps1 (9172 bytes)",
                "sha256": hash_stop_bak,
                "target_sha256": hash_stop_ps1,
                "notes": "Pre-modification backup of stop.ps1 created during previous scripting passes.",
                "action_recommendation": "MOVE_TO_ARCHIVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\llama-swap\\config.yaml.backup.20260905_105239",
                "type": "FILE",
                "size_bytes": 1006,
                "comparison_target": "K:\\Project\\llama-swap\\config.yaml (2264 bytes)",
                "notes": "Timestamped backup of config.yaml before 3-model team configuration was deployed.",
                "action_recommendation": "MOVE_TO_ARCHIVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\OpenHands",
                "type": "DIRECTORY",
                "file_count": 0,
                "total_size_bytes": 0,
                "comparison_target": "None",
                "notes": "Completely empty directory remnant.",
                "action_recommendation": "SAFE_TO_REMOVE_IN_STAGE_6B"
            }
        ],
        "OLD_TEST_ARTIFACT": [
            {
                "item": "K:\\Project\\Three-Model-Integration-Full-Archive.zip",
                "type": "FILE",
                "size_bytes": 11931770,
                "notes": "Historical packaged test evidence from Stage 3/4 integration.",
                "action_recommendation": "MOVE_TO_ARCHIVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\Three-Model-Integration-Supplemental-Evidence.zip",
                "type": "FILE",
                "size_bytes": 12745550,
                "notes": "Historical supplemental evidence archive.",
                "action_recommendation": "MOVE_TO_ARCHIVE_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\llama.log",
                "type": "FILE",
                "size_bytes": 3358,
                "sha256": hash_root_llama_log,
                "notes": "Scattered log file in root directory.",
                "action_recommendation": "MOVE_TO_LOGS_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\Models\\smoke_test.err.log",
                "type": "FILE",
                "size_bytes": 14512,
                "notes": "Misplaced stderr smoke test log in Models directory.",
                "action_recommendation": "MOVE_TO_LOGS_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\Models\\smoke_test.out.log",
                "type": "FILE",
                "size_bytes": 2864,
                "notes": "Misplaced stdout smoke test log in Models directory.",
                "action_recommendation": "MOVE_TO_LOGS_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\all_modes_results.json",
                "type": "FILE",
                "size_bytes": 5014,
                "notes": "Scattered test result JSON in root directory.",
                "action_recommendation": "MOVE_TO_TESTS_IN_STAGE_6B"
            },
            {
                "item": "K:\\Project\\Root_Test_Python_Scripts",
                "type": "FILE_COLLECTION",
                "count": 31,
                "sample_files": [
                    "test_all_modes.py",
                    "test_barge_in.py",
                    "test_budget.py",
                    "test_combined_memory.py",
                    "test_litellm.py",
                    "benchmark_voice_full.py",
                    "inspect_conv_req.py"
                ],
                "notes": "Standalone investigative and benchmark test scripts placed in root during early stages.",
                "action_recommendation": "MOVE_TO_TESTS_LEGACY_ROOT_IN_STAGE_6B"
            }
        ],
        "ACTIVE_PRODUCTION": [
            {
                "item": "K:\\Project\\Models\\Qwen3.8\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
                "type": "FILE",
                "size_bytes": 16810714688,
                "notes": "Target canonical copy on K:. Copied and SHA256 verified in Stage 6A."
            },
            {
                "item": "D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
                "type": "FILE",
                "size_bytes": 16810714688,
                "notes": "Current production reference in llama-swap config.yaml. PRESERVED and untouched."
            },
            {
                "item": "K:\\Project\\Models\\Ornith-1.5-35B-MTP-19G-ICE.gguf",
                "type": "FILE",
                "size_bytes": 18822546944,
                "notes": "Active production model for Ornith coding agent."
            },
            {
                "item": "K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf",
                "type": "FILE",
                "size_bytes": 35494473888,
                "notes": "Active production model for Heavy reasoning agent."
            },
            {
                "item": "K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf",
                "type": "FILE",
                "size_bytes": 1507217408,
                "notes": "Active draft model for Qwen3-Next speculative decoding."
            },
            {
                "item": "K:\\Project\\ik_llama\\bin\\llama-server.exe",
                "type": "FILE",
                "notes": "Active production backend for Qwen 3.8 and Ornith."
            },
            {
                "item": "K:\\Project\\llama-mainline\\b10816\\llama-server.exe",
                "type": "FILE",
                "notes": "Active production backend for Qwen3-Next."
            },
            {
                "item": "K:\\Project\\llama-swap\\bin\\llama-swap.exe",
                "type": "FILE",
                "notes": "Active production model router."
            },
            {
                "item": "K:\\Project\\transcribe-build-shared\\bin\\Release\\transcribe.dll",
                "type": "FILE",
                "notes": "Active STT library dynamically loaded by local-voice service."
            }
        ],
        "UNCERTAIN_DO_NOT_TOUCH": [
            {
                "item": "K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q6_K.gguf",
                "type": "FILE",
                "size_bytes": 1873725440,
                "notes": "Alternative higher-precision draft model quant. Currently inactive (active uses Q4_K_M). Retain for reference/benchmarking."
            },
            {
                "item": "K:\\Project\\Models\\Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF.gguf",
                "type": "FILE",
                "size_bytes": 44612547968,
                "notes": "Benchmark 122B model weights. Not part of daily active 3-model production set, but large and valuable. Keep untouched."
            },
            {
                "item": "K:\\Project\\Models\\Qwen3.5-122B-A10B-44GB-GPT5.6Sol-SFT-LynnStyle-GGUF-mmproj-Q8_0.gguf",
                "type": "FILE",
                "size_bytes": 619212000,
                "notes": "Vision companion for 122B benchmark model. Keep untouched."
            }
        ]
    },
    "counts": {
        "safe_duplicate_candidates_count": 6,
        "old_test_artifacts_count": 37,
        "active_production_items_count": 9,
        "uncertain_do_not_touch_count": 3
    }
}

with open(os.path.join(evidence_dir, "duplicate_candidates.json"), "w", encoding="utf-8") as f:
    json.dump(duplicate_candidates_data, f, indent=2, ensure_ascii=False)
print("duplicate_candidates.json created.")
