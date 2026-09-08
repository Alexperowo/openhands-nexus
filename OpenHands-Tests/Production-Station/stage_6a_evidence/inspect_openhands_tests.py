import os

p = r"K:\Project\OpenHands-Tests"
for item in sorted(os.listdir(p)):
    full = os.path.join(p, item)
    if os.path.isdir(full):
        print(f"  [DIR]  {item}")
    else:
        print(f"  [FILE] {item} ({os.path.getsize(full)} bytes)")
