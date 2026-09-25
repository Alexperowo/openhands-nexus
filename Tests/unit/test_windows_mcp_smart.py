"""Unit tests for smart Computer Use tools in windows-mcp."""

import sys
from pathlib import Path

# Add windows-mcp to path
windows_mcp_dir = Path(__file__).resolve().parents[2] / "windows-mcp"
if str(windows_mcp_dir) not in sys.path:
    sys.path.insert(0, str(windows_mcp_dir))

import server


class TestWindowsMcpSmartTools:
    """Test smart tools registration and basic contracts."""

    def test_smart_tools_registered(self):
        """Verify all smart Computer Use tools are properly registered on the MCP instance."""
        tools = server.mcp._tool_manager._tools
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
        assert len(tools) == 27, f"Expected 27 tools, found {len(tools)}"
        for tool_name in expected_tools:
            assert tool_name in tools, f"Expected tool '{tool_name}' not registered on FastMCP server"

    def test_screen_info(self):
        """Test getting physical screen dimensions and mouse cursor."""
        info = server.desktop_get_screen_info()
        assert "screen_width" in info
        assert "screen_height" in info
        assert info["screen_width"] > 0
        assert info["screen_height"] > 0

    def test_list_elements_taskbar(self):
        """Test listing UI elements on Taskbar via UI Automation."""
        elements = server.desktop_list_elements("taskbar", max_elements=10)
        assert isinstance(elements, list)
        assert len(elements) > 0
        first = elements[0]
        assert "name" in first
        assert "center_x" in first
        assert "center_y" in first

    def test_find_text_ocr(self):
        """Test running native Windows OCR on the screen or taskbar."""
        # Querying an empty or common word
        matches = server.desktop_find_text_ocr(query="2026", window_title="taskbar")
        assert isinstance(matches, list)

    def test_region_screenshot_contract(self):
        """Test capturing 1:1 region screenshot returns valid PNG Image."""
        img_obj = server.desktop_take_region_screenshot(x=0, y=0, width=50, height=50)
        assert img_obj._format == "png"
        assert isinstance(img_obj.data, bytes)
        assert len(img_obj.data) > 0
