import os, shutil, json, datetime

root = r"K:\Project"
evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_evidence"

# 1. Prepare target directories
target_dirs = [
    r"K:\Project\Tests\legacy_root",
    r"K:\Project\Archive\backups",
    r"K:\Project\Archive\zip_archives",
    r"K:\Project\Archive\deprecated_builds",
    r"K:\Project\Logs\legacy",
    r"K:\Project\Docs"
]

for td in target_dirs:
    os.makedirs(td, exist_ok=True)
    print("Ensured target directory:", td)

# 2. Production scripts to check references against
prod_scripts = [
    r"K:\Project\START-OPENHANDS-LOCAL.cmd",
    r"K:\Project\STOP-OPENHANDS-LOCAL.cmd",
    r"K:\Project\RESTART-OPENHANDS-LOCAL.cmd",
    r"K:\Project\DIAGNOSTICS-OPENHANDS-LOCAL.cmd",
    r"K:\Project\.openhands-local\start.ps1",
    r"K:\Project\.openhands-local\stop.ps1",
    r"K:\Project\.openhands-local\diagnostics.ps1",
    r"K:\Project\llama-swap\config.yaml",
    r"K:\Project\local-voice\service.py",
    r"K:\Project\openhands-localization\patch-agent-canvas-localization.ps1"
]

prod_text = ""
for ps in prod_scripts:
    if os.path.exists(ps):
        with open(ps, "r", encoding="utf-8", errors="ignore") as f:
            prod_text += f.read() + "\n"

# 3. Define relocation list
relocations = []

# Legacy root python test scripts
root_py = [
    "benchmark_voice_full.py", "inspect_conv_req.py", "setup_openhands_profiles.py",
    "verify_openhands_profiles.py", "test_all_modes.py", "test_barge_in.py",
    "test_bgt.py", "test_budget.py", "test_comb.py", "test_combined_memory.py",
    "test_compare.py", "test_direct2.py", "test_direct_deepseek.py",
    "test_direct_inst.py", "test_direct_prompt.py", "test_exact.py",
    "test_futo_stt.py", "test_jinja_render.py", "test_litellm.py",
    "test_litellm_both.py", "test_litellm_budget.py", "test_litellm_direct.py",
    "test_off_modes.py", "test_persistent_stt.py", "test_raw_prompt.py",
    "test_reasoning_syntax.py", "test_rf.py", "test_save_profile.py",
    "test_single_profile.py", "test_val.py", "test_voice_bridge_stt.py",
    "test_voice_bridge_tts.py"
]

for py in root_py:
    relocations.append({
        "source": os.path.join(root, py),
        "destination": os.path.join(root, "Tests", "legacy_root", py),
        "action": "RELOCATE_ROOT_TEST_SCRIPT"
    })

# Root test results
relocations.append({
    "source": os.path.join(root, "all_modes_results.json"),
    "destination": os.path.join(root, "Tests", "legacy_root", "all_modes_results.json"),
    "action": "RELOCATE_ROOT_TEST_RESULT"
})

# Historical archives
for arc in ["Three-Model-Integration-Full-Archive.zip", "Three-Model-Integration-Supplemental-Evidence.zip"]:
    relocations.append({
        "source": os.path.join(root, arc),
        "destination": os.path.join(root, "Archive", "zip_archives", arc),
        "action": "RELOCATE_HISTORICAL_ARCHIVE"
    })

# Backups
for bak in [
    (r"K:\Project\.openhands-local\start.ps1.bak", r"K:\Project\Archive\backups\start.ps1.bak"),
    (r"K:\Project\.openhands-local\stop.ps1.bak", r"K:\Project\Archive\backups\stop.ps1.bak"),
    (r"K:\Project\llama-swap\config.yaml.backup.20260905_105239", r"K:\Project\Archive\backups\config.yaml.backup.20260905_105239")
]:
    relocations.append({
        "source": bak[0],
        "destination": bak[1],
        "action": "RELOCATE_BACKUP_FILE"
    })

# Scattered test logs
for lg in [
    (r"K:\Project\llama.log", r"K:\Project\Logs\legacy\llama.log"),
    (r"K:\Project\Models\smoke_test.err.log", r"K:\Project\Logs\legacy\smoke_test.err.log"),
    (r"K:\Project\Models\smoke_test.out.log", r"K:\Project\Logs\legacy\smoke_test.out.log")
]:
    relocations.append({
        "source": lg[0],
        "destination": lg[1],
        "action": "RELOCATE_SCATTERED_LOG"
    })

# Documentation & reference media
for doc in [
    (r"K:\Project\ik_llama_help.txt", r"K:\Project\Docs\ik_llama_help.txt"),
    (r"K:\Project\final_about_tablet.png", r"K:\Project\Docs\final_about_tablet.png")
]:
    relocations.append({
        "source": doc[0],
        "destination": doc[1],
        "action": "RELOCATE_DOCUMENTATION"
    })

manifest = []

for item in relocations:
    src = item["source"]
    dst = item["destination"]
    act = item["action"]
    fname = os.path.basename(src)
    
    if not os.path.exists(src):
        manifest.append({
            "SOURCE": src,
            "DESTINATION": dst,
            "SIZE": 0,
            "ACTION": act,
            "REFERENCE_CHECK": "SKIPPED_SOURCE_NOT_FOUND",
            "RESULT": "NOT_FOUND"
        })
        continue
        
    sz = os.path.getsize(src)
    
    # Check reference in production scripts
    ref_found = fname in prod_text
    ref_check_str = "REFERENCED_IN_PROD_ERROR" if ref_found else "NO_PRODUCTION_REFERENCE_CLEAN"
    
    if ref_found:
        print(f"ERROR: Reference found for {fname} in production scripts! Aborting move.")
        manifest.append({
            "SOURCE": src,
            "DESTINATION": dst,
            "SIZE": sz,
            "ACTION": act,
            "REFERENCE_CHECK": ref_check_str,
            "RESULT": "ABORTED_REF_FOUND"
        })
        continue
        
    # Execute move
    try:
        shutil.move(src, dst)
        dst_exists = os.path.exists(dst)
        dst_sz = os.path.getsize(dst) if dst_exists else -1
        if dst_exists and dst_sz == sz:
            res_str = "SUCCESS"
        else:
            res_str = "SIZE_MISMATCH"
    except Exception as e:
        res_str = f"ERROR: {e}"
        
    manifest.append({
        "SOURCE": src,
        "DESTINATION": dst,
        "SIZE": sz,
        "ACTION": act,
        "REFERENCE_CHECK": ref_check_str,
        "RESULT": res_str
    })
    print(f"Moved: {fname} -> {res_str}")

# Remove empty OpenHands directory
openhands_dir = r"K:\Project\OpenHands"
openhands_del_status = "NOT_ATTEMPTED"
if os.path.exists(openhands_dir):
    contents = os.listdir(openhands_dir)
    if len(contents) == 0:
        try:
            os.rmdir(openhands_dir)
            openhands_del_status = "DELETED_CONFIRMED_EMPTY"
            print("Removed empty directory:", openhands_dir)
        except Exception as e:
            openhands_del_status = f"FAILED: {e}"
    else:
        openhands_del_status = "ABORTED_NOT_EMPTY"

manifest_data = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "stage": "STAGE_6B",
    "total_files_relocated": sum(1 for m in manifest if m["RESULT"] == "SUCCESS"),
    "total_directories_deleted": 1 if openhands_del_status == "DELETED_CONFIRMED_EMPTY" else 0,
    "empty_directory_removal": {
        "path": openhands_dir,
        "status": openhands_del_status
    },
    "manifest": manifest
}

with open(os.path.join(evidence_dir, "relocation_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest_data, f, indent=2, ensure_ascii=False)
print("relocation_manifest.json saved.")
