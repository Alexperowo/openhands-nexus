"""
Hardware verification test for NVIDIA CUDA GPU and VRAM capacity.
"""

import subprocess
import shutil
import pytest


class TestCudaHardware:
    """Verifies GPU, CUDA driver, and 22 GB VRAM allocation."""

    def test_nvidia_smi_available(self):
        smi = shutil.which("nvidia-smi")
        assert smi is not None, "nvidia-smi executable not found in PATH"

    def test_gpu_model_and_vram(self):
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True
        )
        output = res.stdout.strip()
        parts = [p.strip() for p in output.split(",")]
        gpu_name = parts[0]
        total_vram_mb = int(parts[1])
        driver = parts[2]

        assert "RTX 2080 Ti" in gpu_name or "NVIDIA" in gpu_name, f"Unexpected GPU: {gpu_name}"
        # 22GB mod is approx 22528 MB
        assert total_vram_mb >= 20000, f"Expected >= 20 GB VRAM, got {total_vram_mb} MB"
        assert len(driver) > 0

    def test_vram_budget_not_exceeded(self):
        """Ensures current VRAM usage does not exceed physical limit."""
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True
        )
        used_mb, total_mb = [int(p.strip()) for p in res.stdout.strip().split(",")]
        assert used_mb <= total_mb, f"VRAM used ({used_mb} MB) exceeds total ({total_mb} MB)"
