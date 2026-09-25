"""Windows Computer Use MCP Server.

Provides tools for desktop automation, screen capture, mouse and keyboard control,
UI Automation accessibility tree inspection, native OCR, and window management on Windows.
"""

import concurrent.futures
import ctypes
import io
import time
from ctypes import wintypes
from typing import Any

# Ensure the process/thread is attached to interactive desktop before any GUI/COM hooks
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def _ensure_desktop() -> None:
    """Ensure the calling thread is attached to the interactive desktop."""
    try:
        user32.SetProcessDPIAware()
        desk = user32.OpenInputDesktop(0, False, 0x01FF)
        if desk:
            user32.SetThreadDesktop(desk)
    except Exception:
        pass


_ensure_desktop()

import pyautogui
import winocr
from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage
from PIL import ImageGrab
from playwright.async_api import async_playwright
from pywinauto import Desktop

# Safety settings for pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

mcp = FastMCP("windows-computer-use")

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


def _find_target_window_win32(window_title: str = ""):
    """Find top-level window by title substring or alias via pure Win32 API.

    Returns (hwnd, title, class_name, (left, top, right, bottom)) or None.
    """
    _ensure_desktop()
    if not window_title:
        hwnd = user32.GetForegroundWindow()
        if hwnd and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return (hwnd, "foreground", "foreground", (rect.left, rect.top, rect.right, rect.bottom))

    matched = None
    q = (window_title or "").lower().strip()

    if q in ("taskbar", "панель задач"):
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if hwnd and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return (hwnd, "Shell_TrayWnd", "Shell_TrayWnd", (rect.left, rect.top, rect.right, rect.bottom))

    if q in ("desktop", "рабочий стол"):
        hwnd = user32.FindWindowW("Progman", None) or user32.GetDesktopWindow()
        if hwnd and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return (hwnd, "Desktop", "Progman", (rect.left, rect.top, rect.right, rect.bottom))

    def cb(hwnd, _lparam):
        nonlocal matched
        if user32.IsWindowVisible(hwnd):
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls_name = cls_buf.value.strip()

            title = ""
            title_len = user32.GetWindowTextLengthW(hwnd)
            if title_len > 0:
                buf = ctypes.create_unicode_buffer(title_len + 1)
                user32.GetWindowTextW(hwnd, buf, title_len + 1)
                title = buf.value.strip()

            is_match = False
            if not q:
                if cls_name == "Shell_TrayWnd" or title_len > 0:
                    is_match = True
            elif q in ("taskbar", "панель задач") and cls_name == "Shell_TrayWnd" or q in ("desktop", "рабочий стол") and cls_name in ("Progman", "WorkerW") or title and q in title.lower() or q in cls_name.lower():
                is_match = True

            if is_match:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                matched = (hwnd, title or cls_name, cls_name, (rect.left, rect.top, rect.right, rect.bottom))
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return matched


def _find_target_window(window_title: str = ""):
    """Find pywinauto WindowSpecification by targeting the HWND found via Win32."""
    target = _find_target_window_win32(window_title)
    if not target:
        return None
    hwnd = target[0]
    d = Desktop(backend="uia")
    try:
        return d.window(handle=hwnd)
    except Exception:
        return None


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
    """Take a full screenshot of the entire desktop.

    Args:
        max_width: Maximum width in pixels to downsample to (preserves aspect ratio). Default 1920.
    """
    _ensure_desktop()
    img = ImageGrab.grab(all_screens=False)
    if max_width and img.width > max_width:
        ratio = max_width / float(img.width)
        new_height = int(float(img.height) * ratio)
        img = img.resize((max_width, new_height), PILImage.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
def desktop_take_window_screenshot(window_title: str = "", max_width: int = 2560) -> Image:
    """Take a screenshot of a specific window at 100% native 1:1 scale without downsampling blur.

    Preserves fine fonts, terminal characters, and small button text on 4K displays.

    Args:
        window_title: Title or substring of the window to capture. If empty, captures active foreground window.
        max_width: Maximum width before downsampling. Default 2560 (keeps standard windows at 1:1 scale).
    """
    _ensure_desktop()
    target = _find_target_window_win32(window_title)
    if not target:
        return desktop_take_screenshot(max_width=max_width)

    hwnd, title, cls_name, (left, top, right, bottom) = target
    if left == -32000 or (right - left) <= 0 or (bottom - top) <= 0:
        try:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.1)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass

    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    if max_width and img.width > max_width:
        ratio = max_width / float(img.width)
        new_height = int(float(img.height) * ratio)
        img = img.resize((max_width, new_height), PILImage.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
def desktop_take_region_screenshot(x: int, y: int, width: int, height: int) -> Image:
    """Take a screenshot of a specific bounding box at 100% native 1:1 scale.

    Ideal for zoom-in inspection of small buttons, text, status bars, or dialogs.

    Args:
        x: Left pixel coordinate.
        y: Top pixel coordinate.
        width: Width of the region.
        height: Height of the region.
    """
    _ensure_desktop()
    left = max(0, x)
    top = max(0, y)
    right = left + max(10, width)
    bottom = top + max(10, height)
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
def desktop_list_elements(window_title: str = "", max_elements: int = 60) -> list[dict[str, Any]]:
    """List interactive UI elements (buttons, inputs, menu items, tabs, list items) in a window.

    Returns exact names, element types, and physical screen coordinates (center_x, center_y).
    Works for BOTH multimodal vision models and pure text models (Qwen 122B, Next 80B).

    Args:
        window_title: Title or substring of the window to inspect. If empty, inspects foreground window.
                      Special aliases: 'taskbar' (панель задач) or 'desktop' (рабочий стол).
        max_elements: Maximum number of elements to return.
    """
    _ensure_desktop()
    w = _find_target_window(window_title)
    if not w:
        return [{"error": f"Window matching '{window_title}' not found"}]

    interactive_types = {
        "Button", "Edit", "ListItem", "MenuItem", "TabItem",
        "CheckBox", "RadioButton", "ComboBox", "Hyperlink", "Text", "Pane"
    }

    elements = []
    seen = set()
    try:
        for c in w.descendants():
            ctype = c.friendly_class_name()
            txt = (c.window_text() or "").strip()
            rect = c.rectangle()
            if not txt or rect.width() <= 0 or rect.height() <= 0:
                continue
            key = (txt, rect.left, rect.top)
            if key in seen:
                continue
            seen.add(key)

            if ctype in interactive_types or len(txt) <= 60:
                elements.append({
                    "name": txt,
                    "type": ctype,
                    "center_x": rect.mid_point().x,
                    "center_y": rect.mid_point().y,
                    "rect": [rect.left, rect.top, rect.right, rect.bottom]
                })
                if len(elements) >= max_elements:
                    break
    except Exception as e:
        elements.append({"warning": f"Partial enumeration due to: {e}"})

    return elements


@mcp.tool()
def desktop_find_text_ocr(query: str, window_title: str = "", lang: str = "ru") -> list[dict[str, Any]]:
    """Find words or phrases on screen using Windows 11 native OCR engine.

    Returns exact bounding boxes and physical screen center coordinates (center_x, center_y).
    Use this for non-standard UI, game windows, canvas elements, or images without accessibility metadata.

    Args:
        query: Substring or word to find (case-insensitive).
        window_title: Window title or alias ('taskbar', 'desktop'). If empty, scans the entire screen.
        lang: OCR language profile ('ru' or 'en'). Default 'ru'.
    """
    _ensure_desktop()
    target = _find_target_window_win32(window_title) if window_title else None
    if target:
        left, top, right, bottom = target[3]
    else:
        left, top, right, bottom = 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            res = pool.submit(winocr.recognize_pil_sync, img, lang=lang).result()
    except Exception as e:
        return [{"error": f"OCR recognition failed: {e}"}]

    q_lower = query.lower().strip()
    matches = []
    for line in res.get("lines", []):
        for word in line.get("words", []):
            txt = word.get("text", "")
            if q_lower in txt.lower():
                brect = word.get("bounding_rect", {})
                bx = left + brect.get("x", 0)
                by = top + brect.get("y", 0)
                bw = brect.get("width", 0)
                bh = brect.get("height", 0)
                matches.append({
                    "text": txt,
                    "center_x": int(bx + bw / 2),
                    "center_y": int(by + bh / 2),
                    "rect": [int(bx), int(by), int(bx + bw), int(by + bh)]
                })
    return matches


@mcp.tool()
def desktop_click_element(
    name: str,
    window_title: str = "",
    clicks: int = 1,
    button: str = "left"
) -> str:
    """Smart click on a UI element (button, icon, tab, menu, link) by its label or text.

    Intelligently combines UI Automation tree search with native OCR fallback:
    1. First searches UI Automation accessibility tree for matching name.
    2. If not found in tree, falls back to Windows native OCR scanning.
    3. Moves cursor and performs click at exact physical center of the element.

    Args:
        name: Name, label, or text of the element (e.g. 'Пуск', 'Старт', 'Закрыть', 'OK', 'Save').
        window_title: Optional window title substring. If empty, searches foreground window, then all windows.
        clicks: 1 for single click, 2 for double click.
        button: 'left', 'right', or 'middle'. Default 'left'.
    """
    _ensure_desktop()
    name_clean = name.strip().lower()

    candidates = []
    w = _find_target_window(window_title) if window_title else None
    windows_to_search = [w] if w else Desktop(backend="uia").windows()

    matched_pos = None
    matched_label = None
    matched_source = None

    # Step 1: UI Automation exact match
    for win in windows_to_search:
        if not win:
            continue
        try:
            for c in win.descendants():
                txt = (c.window_text() or "").strip()
                rect = c.rectangle()
                if not txt or rect.width() <= 0 or rect.height() <= 0:
                    continue
                if len(candidates) < 10 and c.friendly_class_name() in ("Button", "ListItem", "MenuItem", "TabItem"):
                    candidates.append(f"{c.friendly_class_name()} '{txt}'")

                if txt.lower() == name_clean:
                    matched_pos = (rect.mid_point().x, rect.mid_point().y)
                    matched_label = txt
                    matched_source = f"UI Automation ({c.friendly_class_name()})"
                    break
            if matched_pos:
                break
        except Exception:
            continue

    # Step 1.5: UI Automation substring match if exact match not found
    if not matched_pos:
        for win in windows_to_search:
            if not win:
                continue
            try:
                for c in win.descendants():
                    txt = (c.window_text() or "").strip()
                    rect = c.rectangle()
                    if not txt or rect.width() <= 0 or rect.height() <= 0:
                        continue
                    if name_clean in txt.lower():
                        matched_pos = (rect.mid_point().x, rect.mid_point().y)
                        matched_label = txt
                        matched_source = f"UI Automation substring ({c.friendly_class_name()})"
                        break
                if matched_pos:
                    break
            except Exception:
                continue

    # Step 2: OCR Fallback if UIA did not locate the element
    if not matched_pos:
        ocr_matches = desktop_find_text_ocr(query=name, window_title=window_title)
        if ocr_matches and "error" not in ocr_matches[0]:
            first = ocr_matches[0]
            matched_pos = (first["center_x"], first["center_y"])
            matched_label = first["text"]
            matched_source = "Windows Native OCR"

    if matched_pos:
        cx, cy = matched_pos
        pyautogui.click(x=cx, y=cy, clicks=clicks, button=button)
        return (
            f"Successfully clicked {button} button ({clicks}x) on '{matched_label}' "
            f"at screen coordinates ({cx}, {cy}) via {matched_source}."
        )
    else:
        cand_str = ", ".join(candidates[:8]) if candidates else "none"
        return (
            f"Could not find element '{name}' via UI Automation or OCR. "
            f"Available interactive elements nearby: [{cand_str}]. "
            f"Try calling desktop_list_elements() to see all controls in the window."
        )


@mcp.tool()
def desktop_set_element_text(name: str, text: str, window_title: str = "") -> str:
    """Set text directly into an input field or edit control via Windows UI Automation.

    Bypasses keyboard typing, hotkeys, and keyboard layout/language mismatches.

    Args:
        name: Name, label, or current value of the input field.
        text: Text to set into the control.
        window_title: Window title or substring. If empty, searches foreground window.
    """
    _ensure_desktop()
    w = _find_target_window(window_title)
    if not w:
        return f"Window matching '{window_title}' not found"

    name_lower = name.lower().strip()
    target_ctrl = None
    try:
        for c in w.descendants(control_type="Edit"):
            txt = (c.window_text() or "").strip()
            if name_lower in txt.lower():
                target_ctrl = c
                break
        if not target_ctrl:
            for c in w.descendants():
                txt = (c.window_text() or "").strip()
                if name_lower in txt.lower() and c.friendly_class_name() in ("Edit", "ComboBox", "Pane"):
                    target_ctrl = c
                    break
    except Exception as e:
        return f"Error searching for edit control: {e}"

    if not target_ctrl:
        return f"Input element '{name}' not found in window '{window_title}'"

    try:
        target_ctrl.set_text(text)
        return f"Successfully set text in '{name}' via UI Automation"
    except Exception:
        try:
            target_ctrl.set_focus()
            target_ctrl.type_keys("^a{BACKSPACE}", pause=0.05)
            _type_unicode_text(text)
            return f"Set text in '{name}' via keyboard fallback"
        except Exception as e:
            return f"Failed to set text in '{name}': {e}"


@mcp.tool()
def desktop_invoke_element(name: str, window_title: str = "") -> str:
    """Trigger a button, menu item, or clickable control via UI Automation InvokePattern.

    Executes the click action natively in the OS without moving the mouse pointer.

    Args:
        name: Name or label of the control (e.g. 'OK', 'Сохранить', 'Cancel', 'Start').
        window_title: Window title or substring. If empty, searches foreground window.
    """
    _ensure_desktop()
    w = _find_target_window(window_title)
    if not w:
        return f"Window matching '{window_title}' not found"

    name_lower = name.lower().strip()
    target_ctrl = None
    try:
        for c in w.descendants():
            txt = (c.window_text() or "").strip()
            if name_lower == txt.lower() or (len(name_lower) >= 3 and name_lower in txt.lower()):
                target_ctrl = c
                break
    except Exception as e:
        return f"Error searching for control: {e}"

    if not target_ctrl:
        return f"Element '{name}' not found in window '{window_title}'"

    try:
        target_ctrl.invoke()
        return f"Successfully invoked control '{name}' via UI Automation"
    except Exception:
        try:
            rect = target_ctrl.rectangle()
            cx, cy = rect.mid_point().x, rect.mid_point().y
            pyautogui.click(cx, cy)
            return f"Clicked center of control '{name}' at ({cx}, {cy})"
        except Exception as e:
            return f"Failed to invoke control '{name}': {e}"


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
        user32.ShowWindow(target_hwnd, 9)
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.1)
        return f"Focused window: '{target_title}' (HWND: {target_hwnd})"
    return f"Window matching '{title_substring}' not found"


# ---------------------------------------------------------------------------
# Browser Automation Engine (Playwright / Chrome DevTools Protocol)
# ---------------------------------------------------------------------------

_pw_instance: Any = None
_pw_browser: Any = None
_pw_context: Any = None
_pw_page: Any = None


async def _get_active_browser_page(create_if_missing: bool = True) -> Any:
    """Get active Playwright Page, restoring or recreating if needed."""
    global _pw_instance, _pw_browser, _pw_context, _pw_page
    if _pw_page is not None and not _pw_page.is_closed():
        return _pw_page

    if not create_if_missing:
        return None

    if _pw_instance is None:
        _pw_instance = await async_playwright().start()

    if _pw_browser is None or not _pw_browser.is_connected():
        try:
            _pw_browser = await _pw_instance.chromium.launch(channel="chrome", headless=False)
        except Exception:
            _pw_browser = await _pw_instance.chromium.launch(headless=False)

    if _pw_context is None:
        _pw_context = await _pw_browser.new_context()

    _pw_page = await _pw_context.new_page()
    return _pw_page


@mcp.tool()
async def browser_open(url: str = "about:blank", headless: bool = False, cdp_port: int = 0) -> str:
    """Open Google Chrome and navigate to a URL with 100% deterministic DOM/CDP control.

    Eliminates resolution dependence, 4K DPI scaling issues, and pixel misses.

    Args:
        url: The URL to navigate to (e.g. 'https://colab.research.google.com').
        headless: Whether to run in headless mode (False allows the user to see and interact with the browser).
        cdp_port: If specified (> 0), connects to an already-running Chrome instance on this debugging port.
    """
    global _pw_instance, _pw_browser, _pw_context, _pw_page

    if _pw_instance is None:
        _pw_instance = await async_playwright().start()

    if cdp_port > 0:
        if _pw_browser:
            try:
                await _pw_browser.close()
            except Exception:
                pass
        _pw_browser = await _pw_instance.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        contexts = _pw_browser.contexts
        _pw_context = contexts[0] if contexts else await _pw_browser.new_context()
        pages = _pw_context.pages
        _pw_page = pages[0] if pages else await _pw_context.new_page()
    else:
        if _pw_browser is None or not _pw_browser.is_connected():
            try:
                _pw_browser = await _pw_instance.chromium.launch(channel="chrome", headless=headless)
            except Exception:
                _pw_browser = await _pw_instance.chromium.launch(headless=headless)
            _pw_context = await _pw_browser.new_context()
            _pw_page = await _pw_context.new_page()

    if url and _pw_page:
        await _pw_page.goto(url, wait_until="domcontentloaded")
        title = await _pw_page.title()
        return f"Opened '{url}' (Title: '{title}')"

    return "Browser opened successfully"


@mcp.tool()
async def browser_click(selector: str, timeout_ms: int = 10000) -> str:
    """Click an element in the browser page using CSS selector, text, XPath, or ARIA role.

    Works with 100% precision regardless of screen resolution or 4K scaling.

    Args:
        selector: CSS selector (e.g. '#run-all', '.btn-primary'), text (e.g. 'text=Run'), or ARIA role (e.g. \"role=button[name='Connect']\").
        timeout_ms: Timeout in milliseconds to wait for the element. Default 10000.
    """
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return "Error: No active browser page. Call browser_open first."

    try:
        await page.click(selector, timeout=timeout_ms)
        return f"Clicked browser element matching '{selector}'"
    except Exception as e:
        return f"Failed to click '{selector}': {e}"


@mcp.tool()
async def browser_type(selector: str, text: str, clear_first: bool = True) -> str:
    """Type text into an input, textarea, or contenteditable element in the browser.

    Args:
        selector: CSS selector or text locator for the target field.
        text: The text string to enter.
        clear_first: Whether to clear existing content before typing. Default True.
    """
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return "Error: No active browser page. Call browser_open first."

    try:
        if clear_first:
            await page.fill(selector, text)
        else:
            await page.type(selector, text)
        return f"Typed {len(text)} characters into '{selector}'"
    except Exception as e:
        return f"Failed to type into '{selector}': {e}"


@mcp.tool()
async def browser_press_key(key: str) -> str:
    """Press a keyboard key or combination in the active browser tab.

    Examples: 'Enter', 'Control+Enter', 'Shift+Enter', 'Tab', 'Escape', 'Backspace'.
    """
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return "Error: No active browser page. Call browser_open first."

    try:
        await page.keyboard.press(key)
        return f"Pressed '{key}' in browser"
    except Exception as e:
        return f"Failed to press '{key}': {e}"


@mcp.tool()
async def browser_get_content(selector: str = "", max_length: int = 4000) -> str:
    """Get text content or HTML of an element or entire page.

    Args:
        selector: Optional CSS selector. If empty, returns text of entire page body.
        max_length: Maximum characters to return. Default 4000.
    """
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return "Error: No active browser page. Call browser_open first."

    try:
        if selector:
            text = await page.inner_text(selector)
        else:
            text = await page.inner_text("body")
        if len(text) > max_length:
            text = text[:max_length] + f"\n... [truncated, {len(text) - max_length} more characters]"
        return text
    except Exception as e:
        return f"Failed to read content: {e}"


@mcp.tool()
async def browser_wait_for(selector: str, timeout_ms: int = 15000, state: str = "visible") -> str:
    """Wait for an element to satisfy a state ('visible', 'attached', 'detached', 'hidden').

    Args:
        selector: CSS selector, text, or XPath to wait for.
        timeout_ms: Timeout in milliseconds. Default 15000.
        state: Target state ('visible', 'hidden', 'attached', 'detached'). Default 'visible'.
    """
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return "Error: No active browser page. Call browser_open first."

    try:
        await page.wait_for_selector(selector, timeout=timeout_ms, state=state)
        return f"Element '{selector}' reached state '{state}'"
    except Exception as e:
        return f"Timeout waiting for '{selector}' ({state}): {e}"


@mcp.tool()
async def browser_evaluate(script: str) -> str:
    """Evaluate a JavaScript expression or script in the browser context and return JSON result.

    Args:
        script: JavaScript expression (e.g. 'document.title', 'window.location.href').
    """
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return "Error: No active browser page. Call browser_open first."

    try:
        import json
        res = await page.evaluate(script)
        return json.dumps(res, ensure_ascii=False) if res is not None else "null"
    except Exception as e:
        return f"JS evaluation error: {e}"


@mcp.tool()
async def browser_take_screenshot(max_width: int = 1920) -> Image:
    """Capture a high-definition screenshot directly from the browser viewport without OS scaling artifacts."""
    page = await _get_active_browser_page(create_if_missing=False)
    if not page:
        return desktop_take_screenshot(max_width=max_width)

    try:
        png_bytes = await page.screenshot(type="png")
        if max_width:
            img = PILImage.open(io.BytesIO(png_bytes))
            if img.width > max_width:
                ratio = max_width / float(img.width)
                new_height = int(float(img.height) * ratio)
                img = img.resize((max_width, new_height), PILImage.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                return Image(data=buf.getvalue(), format="png")
        return Image(data=png_bytes, format="png")
    except Exception:
        return desktop_take_screenshot(max_width=max_width)


@mcp.tool()
async def browser_close() -> str:
    """Close the automated browser instance and release all associated resources."""
    global _pw_instance, _pw_browser, _pw_context, _pw_page
    closed = []
    if _pw_page and not _pw_page.is_closed():
        await _pw_page.close()
        closed.append("page")
    _pw_page = None
    if _pw_context and not _pw_context.is_closed():
        await _pw_context.close()
        closed.append("context")
    _pw_context = None
    if _pw_browser and _pw_browser.is_connected():
        await _pw_browser.close()
        closed.append("browser")
    _pw_browser = None
    if _pw_instance:
        await _pw_instance.stop()
        closed.append("playwright")
    _pw_instance = None

    return f"Browser closed ({', '.join(closed) if closed else 'already stopped'})"


if __name__ == "__main__":
    mcp.run()
