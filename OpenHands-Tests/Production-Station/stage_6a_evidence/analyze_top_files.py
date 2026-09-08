import os, json, datetime

root = r"K:\Project"

# Scan top-level files
top_files = []
for f in os.listdir(root):
    fp = os.path.join(root, f)
    if os.path.isfile(fp):
        stat = os.stat(fp)
        top_files.append({
            "name": f,
            "path": fp,
            "size": stat.st_size,
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
        })

print(f"Total top-level files: {len(top_files)}")
print("Categories of top-level files:")
exts = {}
for tf in top_files:
    ext = os.path.splitext(tf["name"])[1].lower()
    exts[ext] = exts.get(ext, 0) + 1
print(exts)
