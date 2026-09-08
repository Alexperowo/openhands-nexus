import os

print("=== llama-mainline ===")
for root, dirs, files in os.walk(r"K:\Project\llama-mainline"):
    print(root, "dirs:", dirs, "files count:", len(files))

print("=== llama.cpp ===")
for root, dirs, files in os.walk(r"K:\Project\llama.cpp"):
    print(root, "dirs:", dirs, "files count:", len(files))

print("=== .openhands-local/logs ===")
for root, dirs, files in os.walk(r"K:\Project\.openhands-local\logs"):
    print(root, "dirs:", dirs, "files:", files)
