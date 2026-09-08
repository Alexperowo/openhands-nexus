import os, json, datetime

evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6a_evidence"

summary_data = {
    "stage": "STAGE_6A",
    "status": "PASS",
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "k_project_inventoried": "YES (18 top-level directories, 42 top-level files)",
    "production_baseline_unchanged": "YES",
    "qwen38": {
        "source_path": "D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "destination_path": "K:\\Project\\Models\\Qwen3.8\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
        "copy_complete": "YES",
        "hash_verified": "YES",
        "source_preserved": "YES",
        "files_verified": [
            {
                "file": "Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
                "size": 16810714688,
                "sha256": "424b98a8f5add2fb66b92902d98ee9288badc82f4b986e70ade5f8d5ca615991",
                "hash_match": "YES"
            },
            {
                "file": "Qwen3.8-27B-Opus-Distill-v2-mmproj-f16.gguf",
                "size": 927607296,
                "sha256": "de0d58cea206add6ff82392027785ff294ad9cca22b74fc949f4eb15add35512",
                "hash_match": "YES"
            }
        ]
    },
    "ornith_current_path": "K:\\Project\\Models\\Ornith-1.5-35B-MTP-19G-ICE.gguf",
    "next_current_path": "K:\\Project\\Models\\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf",
    "canonical_model_root": "K:\\Project\\Models",
    "proposed_structure": "K:\\Project\\{Models, Backends, Config, Scripts, Runtime, Tests, Logs, Temp, Docs, Archive}",
    "duplicate_candidates_count": 6,
    "obsolete_candidates_count": 34,
    "logs_to_relocate_count": 4,
    "temp_items_to_relocate_count": 4,
    "files_moved": "NONE",
    "files_deleted": "NONE",
    "production_config_changed": "NO",
    "evidence_path": "K:\\Project\\OpenHands-Tests\\Production-Station\\stage_6a_evidence\\",
    "unresolved": "NONE"
}

with open(os.path.join(evidence_dir, "stage_6a_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary_data, f, indent=2, ensure_ascii=False)
print("stage_6a_summary.json created.")
