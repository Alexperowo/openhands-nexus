import os

scripts_to_check = [
    r"K:\Project\START-OPENHANDS-LOCAL.cmd",
    r"K:\Project\STOP-OPENHANDS-LOCAL.cmd",
    r"K:\Project\RESTART-OPENHANDS-LOCAL.cmd",
    r"K:\Project\DIAGNOSTICS-OPENHANDS-LOCAL.cmd",
    r"K:\Project\.openhands-local\start.ps1",
    r"K:\Project\.openhands-local\stop.ps1",
    r"K:\Project\.openhands-local\diagnostics.ps1",
    r"K:\Project\llama-swap\config.yaml"
]

for s in scripts_to_check:
    if os.path.exists(s):
        with open(s, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        print(f"=== References in {os.path.basename(s)} ===")
        for py in os.listdir(r"K:\Project"):
            if py.endswith(".py") and py in content:
                print(f"  calls {py}")
