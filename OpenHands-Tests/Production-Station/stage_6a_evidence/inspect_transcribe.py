import os

def check_short(p):
    print(f"=== {p} ===")
    if os.path.exists(p):
        items = os.listdir(p)
        print("Count:", len(items), "Samples:", items[:10])

check_short(r"K:\Project\transcribe-build")
check_short(r"K:\Project\transcribe-build-shared")
