import os, json, datetime

evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_evidence"

summary_data = {
    "stage": "STAGE_6B",
    "status": "PASS",
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "qwen_production_path": "K:\\Project\\Models\\Qwen3.8\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf",
    "qwen_runtime_path_verified": "YES (PID 5576, command line verified, D: path absent)",
    "qwen_smoke": "PASS (conversation 3065c3e9-e9b5-445d-8219-46f225803202 finished, smoke_test_qwen.txt created)",
    "qwen_d_source_preserved": "YES (16810714688 bytes intact on D:\\Project\\models\\)",
    "root_cleanup": "PASS",
    "before_root_files_count": 42,
    "after_root_files_count": 4,
    "files_relocated_count": 43,
    "directories_relocated_count": 0,
    "files_deleted_count": 0,
    "directories_deleted_count": 1,
    "empty_directory_deleted": "K:\\Project\\OpenHands (0 bytes, 0 files)",
    "llama_cpp_status": "ARCHIVE_CANDIDATE_PENDING_REFERENCE_AUDIT",
    "transcribe_build_status": "ARCHIVE_CANDIDATE_PENDING_REFERENCE_AUDIT",
    "active_backends_moved": "NO",
    "ornith_moved": "NO",
    "next_moved": "NO",
    "production_start_after_change": "PASS",
    "production_stop_after_change": "PASS",
    "evidence_path": "K:\\Project\\OpenHands-Tests\\Production-Station\\stage_6b_evidence\\",
    "unresolved": "NONE"
}

with open(os.path.join(evidence_dir, "stage_6b_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary_data, f, indent=2, ensure_ascii=False)
print("stage_6b_summary.json saved.")
