"""
Unit tests for Russian localization dictionary and UI string parity.
Hardware-independent: runs in < 1 second without GPU.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestRussianLocalization:
    """Validates openhands-localization/ru.json content and integrity."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.locale_file = PROJECT_ROOT / "openhands-localization" / "ru.json"
        assert self.locale_file.exists(), f"Missing ru.json: {self.locale_file}"
        with open(self.locale_file, "r", encoding="utf-8") as f:
            self.locale_data = json.load(f)

    def test_dictionary_not_empty(self):
        assert isinstance(self.locale_data, dict)
        assert len(self.locale_data) > 50, f"Expected rich dictionary, got {len(self.locale_data)} keys"

    def test_essential_ui_keys_present(self):
        essential_keys = [
            "SETTINGS",
            "SAVE",
            "CANCEL",
        ]
        # Check either directly as keys or within nested sections
        all_keys = set(self.locale_data.keys())
        for ek in essential_keys:
            found = ek in all_keys or any(ek.lower() in k.lower() for k in all_keys)
            assert found, f"Essential localization key '{ek}' missing from ru.json"

    def test_no_corrupt_mojibake_or_placeholders(self):
        # Scan through values to ensure proper UTF-8 and no broken encoding
        for k, v in list(self.locale_data.items())[:200]:
            if isinstance(v, str):
                assert "Ã" not in v and "Ð" not in v, f"Potential mojibake in key '{k}': {v}"
                assert "{{UNDEFINED}}" not in v
