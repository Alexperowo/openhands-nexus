"""
Unit tests for OpenHands Nexus configuration and profile integrity.
Hardware-independent: runs in < 1 second without GPU.
"""

import json
import os
import re
from pathlib import Path
import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestLlamaSwapConfig:
    """Validates llama-swap configuration and model definitions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.config_path = PROJECT_ROOT / "llama-swap" / "config.yaml"
        assert self.config_path.exists(), f"Missing config: {self.config_path}"
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def test_llama_swap_structure(self):
        assert "models" in self.config, "config.yaml must have 'models' section"
        assert "healthCheckTimeout" in self.config
        assert self.config["healthCheckTimeout"] >= 60

    def test_three_models_defined(self):
        models = self.config["models"]
        for expected in ["qwen", "ornith", "next"]:
            assert expected in models, f"Model '{expected}' missing from llama-swap models"
            m = models[expected]
            assert "cmd" in m, f"Model '{expected}' missing 'cmd'"
            assert "proxy" in m, f"Model '{expected}' missing 'proxy'"
            assert "unloadTimeout" in m, f"Model '{expected}' missing 'unloadTimeout'"
            assert m["unloadTimeout"] > 0

    def test_model_weights_exist_on_disk(self):
        models = self.config["models"]
        for name, m in models.items():
            cmd = m["cmd"]
            # Extract .gguf paths
            gguf_matches = re.findall(r"([A-Za-z]:\\[^\s]+\.gguf)", cmd)
            assert len(gguf_matches) > 0, f"No .gguf model found in cmd for {name}"
            for g in gguf_matches:
                p = Path(g)
                assert p.exists(), f"Model file for {name} does not exist on disk: {p}"


class TestWorkingProfiles:
    """Validates working profile templates and JSON schema."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.templates_dir = PROJECT_ROOT / "Config" / "working-profile-templates"
        assert self.templates_dir.exists(), f"Missing templates dir: {self.templates_dir}"
        self.template_files = list(self.templates_dir.glob("*.json"))

    def test_templates_count(self):
        # We expect 7 standard profiles
        assert len(self.template_files) >= 7, f"Expected >= 7 profiles, got {len(self.template_files)}"

    def test_template_schemas(self):
        required_fields = ["id", "name", "description"]
        for tf in self.template_files:
            with open(tf, "r", encoding="utf-8") as f:
                data = json.load(f)
            for rf in required_fields:
                assert rf in data, f"Profile template '{tf.name}' missing field '{rf}'"
            assert len(data["id"]) > 0
            assert len(data["name"]) > 0
