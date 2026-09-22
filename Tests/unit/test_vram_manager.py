"""
Unit tests for zero-dependency NVML VRAM Manager (Config/vram_manager.py).
"""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Config.vram_manager import NVMLManager, wait_for_vram_cleanup


class TestVramManager:
    """Verifies NVML ctypes initialization and VRAM monitoring accuracy."""

    def test_nvml_initialization(self):
        manager = NVMLManager()
        assert manager.is_available is True, "NVML failed to initialize via ctypes nvml.dll"
        count = manager.get_device_count()
        assert count >= 1, f"Expected at least 1 NVIDIA GPU, detected {count}"

    def test_gpu_info_structure(self):
        manager = NVMLManager()
        gpus = manager.get_all_gpus()
        assert len(gpus) >= 1
        for g in gpus:
            assert "index" in g
            assert "name" in g
            assert "total_mb" in g
            assert "free_mb" in g
            assert "used_mb" in g
            assert g["total_mb"] > 0
            assert g["free_mb"] >= 0
            assert g["used_mb"] >= 0
            assert g["free_mb"] + g["used_mb"] <= g["total_mb"] + 512  # Driver margin

    def test_dual_gpu_pool(self):
        manager = NVMLManager()
        gpus = manager.get_all_gpus()
        if len(gpus) >= 2:
            total_vram = manager.get_total_vram_mb()
            # Dual-GPU setup: RTX 5060 Ti (16 GB) + RTX 2080 Ti (22 GB) = ~38 GB
            assert total_vram >= 35000, f"Expected total pool >= 35 GB, got {total_vram} MB"
            assert manager.get_total_free_mb() >= 0
            assert manager.get_total_used_mb() > 0

    def test_wait_for_vram_cleanup_fast(self):
        # Test with a very low threshold (100 MB free) which should be satisfied immediately
        ok = wait_for_vram_cleanup(target_free_mb_per_gpu=100, timeout_s=2.0)
        assert ok is True
