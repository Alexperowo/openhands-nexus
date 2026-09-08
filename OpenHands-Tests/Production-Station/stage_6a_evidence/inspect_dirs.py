import os

def list_details(path):
    print(f"=== {path} ===")
    for item in sorted(os.listdir(path)):
        full = os.path.join(path, item)
        if os.path.isdir(full):
            print(f"  [DIR]  {item}")
        else:
            print(f"  [FILE] {item} ({os.path.getsize(full)} bytes)")

list_details(r"K:\Project\.openhands-local")
list_details(r"K:\Project\Models")
