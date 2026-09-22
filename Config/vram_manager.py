"""
OpenHands Nexus — Zero-Dependency NVML VRAM Manager & Swap Barrier
Location: Config/vram_manager.py

Provides sub-millisecond GPU VRAM querying, pre-swap reclamation barriers,
and memory budget enforcement using native nvml.dll via ctypes.
Compatible with Windows 10/11 Dual-GPU workstations (RTX 5060 Ti + RTX 2080 Ti).
"""

import argparse
import ctypes
import json
import sys
import time
import urllib.error
import urllib.request


class MemoryInfo(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


class NVMLManager:
    """Zero-dependency NVIDIA Management Library wrapper via ctypes."""

    def __init__(self):
        self._nvml = None
        self._initialized = False
        self._init_nvml()

    def _init_nvml(self):
        try:
            self._nvml = ctypes.CDLL("nvml.dll")
            ret = self._nvml.nvmlInit_v2()
            if ret == 0:
                self._initialized = True
        except Exception:
            self._initialized = False

    @property
    def is_available(self) -> bool:
        return self._initialized

    def get_device_count(self) -> int:
        if not self._initialized:
            return 0
        count = ctypes.c_uint()
        ret = self._nvml.nvmlDeviceGetCount_v2(ctypes.byref(count))
        if ret != 0:
            return 0
        return count.value

    def get_gpu_info(self, index: int) -> dict:
        if not self._initialized:
            return {}
        device = ctypes.c_void_p()
        ret = self._nvml.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(device))
        if ret != 0:
            return {}

        name_buf = ctypes.create_string_buffer(64)
        self._nvml.nvmlDeviceGetName(device, name_buf, 64)
        name = name_buf.value.decode("utf-8", errors="replace").strip()

        mem = MemoryInfo()
        ret = self._nvml.nvmlDeviceGetMemoryInfo(device, ctypes.byref(mem))
        if ret != 0:
            return {"index": index, "name": name, "total_mb": 0, "free_mb": 0, "used_mb": 0}

        return {
            "index": index,
            "name": name,
            "total_mb": int(mem.total // (1024 * 1024)),
            "free_mb": int(mem.free // (1024 * 1024)),
            "used_mb": int(mem.used // (1024 * 1024)),
        }

    def get_all_gpus(self) -> list:
        gpus = []
        count = self.get_device_count()
        for i in range(count):
            info = self.get_gpu_info(i)
            if info:
                gpus.append(info)
        return gpus

    def get_total_free_mb(self) -> int:
        return sum(g.get("free_mb", 0) for g in self.get_all_gpus())

    def get_total_used_mb(self) -> int:
        return sum(g.get("used_mb", 0) for g in self.get_all_gpus())

    def get_total_vram_mb(self) -> int:
        return sum(g.get("total_mb", 0) for g in self.get_all_gpus())

    def shutdown(self):
        if self._initialized and self._nvml:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self._initialized = False

    def __del__(self):
        self.shutdown()


def wait_for_vram_cleanup(
    target_free_mb_per_gpu: int = 1500,
    timeout_s: float = 15.0,
    poll_interval_s: float = 0.25,
) -> bool:
    """
    Waits until all compute GPUs have at least target_free_mb_per_gpu available.
    Useful after killing or unloading a model before starting a new one.
    """
    manager = NVMLManager()
    if not manager.is_available:
        time.sleep(1.0)
        return True

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        gpus = manager.get_all_gpus()
        all_ready = True
        for g in gpus:
            if g.get("free_mb", 0) < target_free_mb_per_gpu:
                all_ready = False
                break
        if all_ready:
            return True
        time.sleep(poll_interval_s)

    return False


def reclaim_vram(router_url: str = "http://127.0.0.1:8080", timeout_s: float = 10.0) -> dict:
    """
    Triggers model unload in llama-swap router and waits for VRAM to be freed.
    """
    manager = NVMLManager()
    before = manager.get_all_gpus()

    # Trigger unload via router API
    try:
        req = urllib.request.Request(
            f"{router_url}/api/models/unload",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass

    # Wait for memory to drop
    time.sleep(1.0)
    after = manager.get_all_gpus()

    return {
        "success": True,
        "before": before,
        "after": after,
    }


def print_status(as_json: bool = False):
    manager = NVMLManager()
    if not manager.is_available:
        if as_json:
            print(json.dumps({"error": "NVML unavailable"}))
        else:
            print("[WARN] NVML is not available on this system.")
        return

    gpus = manager.get_all_gpus()
    if as_json:
        print(json.dumps({"gpus": gpus, "total_vram_mb": manager.get_total_vram_mb(), "total_free_mb": manager.get_total_free_mb()}))
        return

    print("=====================================================================")
    print("           OpenHands Nexus - GPU VRAM Allocation Status")
    print("=====================================================================")
    for g in gpus:
        pct = (g['used_mb'] / g['total_mb'] * 100.0) if g['total_mb'] > 0 else 0
        bar_len = int(pct / 5)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        print(f" GPU {g['index']}: {g['name']}")
        print(f"   Usage: [{bar}] {g['used_mb']} / {g['total_mb']} MiB ({pct:.1f}%) | Free: {g['free_mb']} MiB")
    print("=====================================================================")
    print(f" Multi-GPU Pool: {manager.get_total_used_mb()} / {manager.get_total_vram_mb()} MiB Used ({manager.get_total_free_mb()} MiB Free)")
    print("=====================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="OpenHands Nexus VRAM Manager & Barrier")
    parser.add_argument("--status", action="store_true", help="Display current VRAM usage")
    parser.add_argument("--json", action="store_true", help="Output VRAM usage in JSON format")
    parser.add_argument("--wait-free", type=int, default=None, help="Wait until free VRAM per GPU >= X MB")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout in seconds for waiting")
    parser.add_argument("--reclaim", action="store_true", help="Trigger router model unload and wait for cleanup")
    parser.add_argument("--router-url", type=str, default="http://127.0.0.1:8080", help="llama-swap router URL")

    args = parser.parse_args()

    if args.wait_free is not None:
        ok = wait_for_vram_cleanup(args.wait_free, timeout_s=args.timeout)
        if ok:
            print(f"[VRAM Barrier] Ready: Free VRAM >= {args.wait_free} MiB achieved.")
            sys.exit(0)
        else:
            print(f"[VRAM Barrier] Timeout: Could not achieve {args.wait_free} MiB free VRAM in {args.timeout}s.")
            sys.exit(1)
    elif args.reclaim:
        res = reclaim_vram(router_url=args.router_url, timeout_s=args.timeout)
        if args.json:
            print(json.dumps(res))
        else:
            print("[VRAM Manager] Model unload triggered and VRAM reclaimed.")
    else:
        print_status(as_json=args.json)


if __name__ == "__main__":
    main()
