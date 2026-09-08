import os, json, datetime

root = r"K:\Project"
evidence_dir = r"K:\Project\OpenHands-Tests\Production-Station\stage_6b_evidence"

items = []
for name in sorted(os.listdir(root)):
    fp = os.path.join(root, name)
    is_dir = os.path.isdir(fp)
    size = 0
    if is_dir:
        count = 0
        try:
            for dp, _, fns in os.walk(fp):
                count += len(fns)
                for f in fns:
                    try:
                        size += os.path.getsize(os.path.join(dp, f))
                    except:
                        pass
        except:
            pass
        items.append({
            "name": name,
            "path": fp,
            "type": "DIRECTORY",
            "file_count": count,
            "total_size_bytes": size
        })
    else:
        try:
            size = os.path.getsize(fp)
        except:
            size = -1
        items.append({
            "name": name,
            "path": fp,
            "type": "FILE",
            "size_bytes": size
        })

root_after_data = {
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "root_path": root,
    "total_items": len(items),
    "directories_count": sum(1 for i in items if i["type"] == "DIRECTORY"),
    "files_count": sum(1 for i in items if i["type"] == "FILE"),
    "items": items
}

with open(os.path.join(evidence_dir, "root_after.json"), "w", encoding="utf-8") as f:
    json.dump(root_after_data, f, indent=2, ensure_ascii=False)
print("root_after.json saved with", len(items), "items.")
print(f"Directories: {root_after_data['directories_count']}, Files: {root_after_data['files_count']}")
for item in items:
    print(f"  [{item['type'][:3]}] {item['name']}")
