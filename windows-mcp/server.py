"""Windows Computer Use MCP Server.

Provides tools for desktop automation, screen capture, mouse and keyboard control,
and window management on Windows.
"""

import ctypes
import io
import time
from ctypes import wintypes
from typing import Any

import pyautogui
from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage
from PIL import ImageGrab

# Safety settings for pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

mcp = FastMCP("windows-computer-use")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


def _type_unicode_text(text: str) -> None:
    """Type arbitrary Unicode text (Cyrillic, Latin, emojis, etc.) directly via Win32 SendInput."""
    inputs = []
    for char in text:
        code = ord(char)
        if code > 0xFFFF:
            code_units = char.encode("utf-16le")
            cu1 = int.from_bytes(code_units[0:2], "little")
            cu2 = int.from_bytes(code_units[2:4], "little")
            for cu in (cu1, cu2):
                inputs.append(INPUT(INPUT_KEYBOARD, INPUT._INPUT(ki=KEYBDINPUT(0, cu, KEYEVENTF_UNICODE, 0, 0))))
                inputs.append(INPUT(INPUT_KEYBOARD, INPUT._INPUT(ki=KEYBDINPUT(0, cu, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))))
        else:
            inputs.append(INPUT(INPUT_KEYBOARD, INPUT._INPUT(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0))))
            inputs.append(INPUT(INPUT_KEYBOARD, INPUT._INPUT(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))))

    if inputs:
        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _ensure_desktop():
    """Ensure the calling thread is attached to the interactive desktop."""
    try:
        user32.SetProcessDPIAware()
        desk = user32.OpenInputDesktop(0, False, 0x01FF)
        if desk:
            user32.SetThreadDesktop(desk)
    except Exception:
        pass


@mcp.tool()
def desktop_get_screen_info() -> dict[str, Any]:
    """Get screen resolution, virtual screen bounds, and current mouse position."""
    _ensure_desktop()
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    pos = pyautogui.position()
    return {
        "screen_width": w,
        "screen_height": h,
        "cursor_x": pos.x,
        "cursor_y": pos.y,
    }


@mcp.tool()
def desktop_take_screenshot(max_width: int = 1920) -> Image:
    """Take a screenshot of the entire desktop.

    Args:
        max_width: Maximum width in pixels to downsample to (preserves aspect ratio, reduces token load). Default 1920.
    """
    _ensure_desktop()
    img = ImageGrab.grab(all_screens=False)
    if img.width > max_width:
        ratio = max_width / float(img.width)
        new_height = int(float(img.height) * ratio)
        img = img.resize((max_width, new_height), PILImage.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
def desktop_mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to specific screen coordinates (x, y)."""
    _ensure_desktop()
    pyautogui.moveTo(x, y)
    return f"Moved cursor to ({x}, {y})"


@mcp.tool()
def desktop_mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Click at specific screen coordinates (x, y).

    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
        button: Mouse button ('left', 'right', 'middle'). Default 'left'.
        clicks: Number of clicks (1 for single click, 2 for double click).
    """
    _ensure_desktop()
    pyautogui.click(x=x, y=y, clicks=clicks, button=button)
    return f"Clicked {button} button ({clicks}x) at ({x}, {y})"


@mcp.tool()
def desktop_mouse_drag(from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5) -> str:
    """Drag mouse from (from_x, from_y) to (to_x, to_y)."""
    _ensure_desktop()
    pyautogui.moveTo(from_x, from_y)
    pyautogui.dragTo(to_x, to_y, duration=duration, button="left")
    return f"Dragged from ({from_x}, {from_y}) to ({to_x}, {to_y})"


@mcp.tool()
def desktop_mouse_scroll(clicks: int) -> str:
    """Scroll mouse wheel. Positive value scrolls up, negative value scrolls down."""
    _ensure_desktop()
    pyautogui.scroll(clicks)
    return f"Scrolled {clicks} clicks"


@mcp.tool()
def desktop_type_text(text: str) -> str:
    """Type arbitrary text via keyboard, supporting all Unicode characters (Russian/Cyrillic, English, symbols)."""
    _ensure_desktop()
    _type_unicode_text(text)
    return f"Typed {len(text)} characters"


@mcp.tool()
def desktop_press_key(key: str) -> str:
    """Press a single keyboard key.

    Supported keys include: 'enter', 'esc', 'tab', 'win', 'backspace', 'delete',
    'space', 'up', 'down', 'left', 'right', 'f1'-'f12', 'ctrl', 'alt', 'shift'.
    """
    _ensure_desktop()
    key_lower = key.lower().strip()
    pyautogui.press(key_lower)
    return f"Pressed key '{key_lower}'"


@mcp.tool()
def desktop_hotkey(keys: list[str]) -> str:
    """Press a combination of keys simultaneously (e.g. ['ctrl', 'c'], ['alt', 'tab'], ['win', 'r'])."""
    _ensure_desktop()
    norm_keys = [k.lower().strip() for k in keys]
    pyautogui.hotkey(*norm_keys)
    return f"Triggered hotkey: {' + '.join(norm_keys)}"


@mcp.tool()
def desktop_list_windows() -> list[dict[str, Any]]:
    """List all open top-level visible windows with titles and geometry."""
    _ensure_desktop()
    windows = []

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 10 and h > 10:
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "left": rect.left,
                            "top": rect.top,
                            "width": w,
                            "height": h,
                        })
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return windows


@mcp.tool()
def desktop_focus_window(title_substring: str) -> str:
    """Bring a window matching title_substring to foreground."""
    _ensure_desktop()
    target_hwnd = None
    target_title = None

    def callback(hwnd, _lparam):
        nonlocal target_hwnd, target_title
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title_substring.lower() in title.lower():
                    target_hwnd = hwnd
                    target_title = title
                    return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    if target_hwnd:
        # Show window normal (SW_RESTORE = 9)
        user32.ShowWindow(target_hwnd, 9)
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.1)
        return f"Focused window: '{target_title}' (HWND: {target_hwnd})"
    return f"Window matching '{title_substring}' not found"


if __name__ == "__main__":
    mcp.run()
