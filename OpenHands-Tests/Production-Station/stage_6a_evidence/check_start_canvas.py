with open(r"K:\Project\.openhands-local\start.ps1", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "agent canvas in background" in line.lower():
        for j in range(max(0, i-5), min(len(lines), i+20)):
            print(f"{j+1}: {lines[j].strip()}")
