with open(r"K:\Project\.openhands-local\start.ps1", "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "openhands" in line.lower() or "python" in line.lower() or "poetry" in line.lower() or "cd " in line.lower():
            print(line.strip())
