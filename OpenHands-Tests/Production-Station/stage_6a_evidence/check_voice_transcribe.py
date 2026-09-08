import os

p = r"K:\Project\local-voice"
for item in os.listdir(p):
    full = os.path.join(p, item)
    if os.path.isfile(full) and item.endswith(('.py', '.json', '.txt', '.cmd', '.ps1')):
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            c = f.read()
            if "transcribe" in c.lower():
                print(f"local-voice/{item} references transcribe")
