import os, json

root = r"K:\Project"
items = os.listdir(root)
dirs = []
files = []

for item in sorted(items):
    full_path = os.path.join(root, item)
    if os.path.isdir(full_path):
        count = 0
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(full_path):
                count += len(filenames)
                for f in filenames:
                    try:
                        total_size += os.path.getsize(os.path.join(dirpath, f))
                    except:
                        pass
        except Exception as e:
            pass
        dirs.append({'name': item, 'path': full_path, 'file_count': count, 'total_size_bytes': total_size})
    else:
        try:
            sz = os.path.getsize(full_path)
        except:
            sz = -1
        files.append({'name': item, 'path': full_path, 'size_bytes': sz})

print("Top-level Directories:")
for d in dirs:
    print(f"  {d['name']}: {d['file_count']} files, {d['total_size_bytes'] / (1024*1024):.2f} MB")

print(f"\nTop-level Files count: {len(files)}")
for f in files:
    print(f"  {f['name']}: {f['size_bytes'] / 1024:.1f} KB")
