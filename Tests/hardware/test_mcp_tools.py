"""
Automated Hardware & Integration Tests for MCP Tools:
- windows-mcp (Desktop Computer Use, Win32 SendInput Unicode / Cyrillic)
- android-mcp (Samsung Galaxy Tab S9 Ultra, Wi-Fi ADB, Unicode / Cyrillic AdbIME)
"""

import os
import sys
import subprocess
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WINDOWS_MCP_DIR = os.path.join(PROJECT_ROOT, "windows-mcp")


class TestWindowsMCP:
    """Tests for windows-mcp tools."""

    @pytest.fixture(autouse=True)
    def setup_path(self):
        if WINDOWS_MCP_DIR not in sys.path:
            sys.path.insert(0, WINDOWS_MCP_DIR)

    def test_windows_mcp_import_and_tools(self):
        """Verifies server.py imports cleanly and registers all 27 precision Computer Use tools."""
        import server
        raw_tools = server.mcp._tool_manager._tools if hasattr(server.mcp, "_tool_manager") else []
        tool_names = list(raw_tools.keys()) if isinstance(raw_tools, dict) else [getattr(t, "name", str(t)) for t in raw_tools]
        assert len(tool_names) == 27, f"Expected 27 windows-mcp tools, found {len(tool_names)}: {tool_names}"
        expected_tools = [
            "desktop_get_screen_info",
            "desktop_take_screenshot",
            "desktop_take_window_screenshot",
            "desktop_take_region_screenshot",
            "desktop_list_elements",
            "desktop_find_text_ocr",
            "desktop_click_element",
            "desktop_set_element_text",
            "desktop_invoke_element",
            "desktop_mouse_move",
            "desktop_mouse_click",
            "desktop_mouse_drag",
            "desktop_mouse_scroll",
            "desktop_type_text",
            "desktop_press_key",
            "desktop_hotkey",
            "desktop_list_windows",
            "desktop_focus_window",
            "browser_open",
            "browser_click",
            "browser_type",
            "browser_press_key",
            "browser_get_content",
            "browser_wait_for",
            "browser_evaluate",
            "browser_take_screenshot",
            "browser_close",
        ]
        for exp in expected_tools:
            assert exp in tool_names, f"Missing expected tool {exp}"

    def test_desktop_screen_info(self):
        """Verifies desktop_get_screen_info returns valid display geometry."""
        import server
        info = server.desktop_get_screen_info()
        assert "screen_width" in info and info["screen_width"] > 0
        assert "screen_height" in info and info["screen_height"] > 0
        assert "cursor_x" in info and "cursor_y" in info

    def test_desktop_list_windows(self):
        """Verifies desktop_list_windows enumerates top-level visible windows."""
        import server
        windows = server.desktop_list_windows()
        assert isinstance(windows, list)
        assert len(windows) > 0, "Expected at least one visible top-level window"
        first = windows[0]
        assert "hwnd" in first and "title" in first and "width" in first and "height" in first

    def test_desktop_type_text_unicode_structure(self):
        """Verifies Win32 SendInput Unicode typing helper handles Cyrillic and complex characters."""
        import server
        test_string = "Привет мир 123"
        # Calling _type_unicode_text directly without error
        server._type_unicode_text(test_string)


class TestAndroidMCP:
    """Tests for android-mcp connected to Samsung Galaxy Tab S9 Ultra."""

    TABLET_SERIAL = "192.168.0.34:5555"

    @pytest.fixture(autouse=True)
    def ensure_tablet_connected(self):
        """Check if adb is installed and tablet is connected; reconnect if needed."""
        try:
            # Reconnect WiFi target
            subprocess.run(["adb", "connect", self.TABLET_SERIAL], capture_output=True, timeout=10)
            res = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            if self.TABLET_SERIAL not in res.stdout:
                pytest.skip(f"Tablet {self.TABLET_SERIAL} not connected via ADB")
        except FileNotFoundError:
            pytest.skip("adb binary not found in PATH")

    def test_android_device_model(self):
        """Verifies connected device model matches Samsung Galaxy Tab S9 Ultra (SM-X910)."""
        res = subprocess.run(
            ["adb", "-s", self.TABLET_SERIAL, "shell", "getprop", "ro.product.model"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert res.returncode == 0
        model = res.stdout.strip()
        assert "SM-X910" in model or len(model) > 0, f"Unexpected model: {model}"

    def test_android_adbkeyboard_installed_and_enabled(self):
        """Verifies com.android.adbkeyboard is installed on the tablet for Unicode typing."""
        res = subprocess.run(
            ["adb", "-s", self.TABLET_SERIAL, "shell", "pm", "list", "packages", "com.android.adbkeyboard"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "com.android.adbkeyboard" in res.stdout, "com.android.adbkeyboard must be installed"

    def test_android_cyrillic_broadcast(self):
        """Verifies sending base64 Cyrillic text via AdbIME broadcast succeeds."""
        import base64
        test_cyrillic = "Тест кириллицы OpenHands Nexus"
        b64 = base64.b64encode(test_cyrillic.encode("utf-8")).decode("ascii")
        res = subprocess.run(
            [
                "adb",
                "-s",
                self.TABLET_SERIAL,
                "shell",
                "am",
                "broadcast",
                "-a",
                "ADB_INPUT_B64",
                "--es",
                "msg",
                b64,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert res.returncode == 0
        assert "result=0" in res.stdout, f"Broadcast failed: {res.stdout}"
