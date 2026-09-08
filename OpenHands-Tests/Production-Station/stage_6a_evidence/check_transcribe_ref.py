with open(r"K:\Project\local-voice\service.py", "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "transcribe" in line.lower():
            print(line.strip())
