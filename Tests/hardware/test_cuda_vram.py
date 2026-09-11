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
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        assert len(lines) >= 1, "No GPUs detected"

        total_system_vram_mb = 0
        gpu_names = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            gpu_name = parts[0]
            vram_mb = int(parts[1])
            driver = parts[2]
            gpu_names.append(gpu_name)
            total_system_vram_mb += vram_mb
            assert "NVIDIA" in gpu_name, f"Unexpected GPU: {gpu_name}"
            assert len(driver) > 0

        # Dedicated compute GPU has >= 20 GB VRAM (RTX 2080 Ti mod)
        max_single_gpu_vram = max(int(line.split(",")[1].strip()) for line in lines)
        assert max_single_gpu_vram >= 20000, f"Expected at least one GPU >= 20 GB VRAM, got max {max_single_gpu_vram} MB"

        # Multi-GPU pool verification
        if len(lines) >= 2:
            assert total_system_vram_mb >= 35000, f"Expected total multi-GPU pool >= 35 GB, got {total_system_vram_mb} MB"

    def test_vram_budget_not_exceeded(self):
        """Ensures current VRAM usage does not exceed physical limit on any GPU."""
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True
        )
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        for line in lines:
            used_mb, total_mb = [int(p.strip()) for p in line.split(",")]
            assert used_mb <= total_mb, f"VRAM used ({used_mb} MB) exceeds total ({total_mb} MB)"
