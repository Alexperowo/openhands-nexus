import os

# Check for any .tmp files in root
root = r"K:\Project"
for f in os.listdir(root):
    if f.endswith(('.tmp', '.temp')):
        print("Found temp file in root:", f)

# Check .log files in root and subdirectories
for item in os.listdir(root):
    full = os.path.join(root, item)
    if os.path.isfile(full) and item.endswith('.log'):
        print("Root log:", item, os.path.getsize(full))
