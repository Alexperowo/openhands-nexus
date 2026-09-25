# windows-mcp

> **MCP-сервер для автономного управления рабочим столом Windows (Computer Use) с поддержкой 4K-дисплеев**

Позволяет локальным ИИ-агентам (OpenHands, Claude Desktop, Antigravity) полноценно управлять компьютером на Windows, включая текстовые модели (Next 80B, Qwen 122B) и мультимодальные модели (Qwen 27B, Ornith 35B):

### 1. Семантическая навигация и смарт-клики (UI Automation & OCR)
* 🎯 `desktop_click_element(name, window_title)`: Умный клик по названию элемента («Пуск», «Старт», ярлыки, кнопки, табы). Сначала ищет в дереве UI Automation с точностью до 1 пикселя; если элемент нестандартный — подключает локальный системный OCR Windows 11. Работает даже для чисто текстовых моделей без зрения!
* 📋 `desktop_list_elements(window_title, max_elements)`: Возвращает список всех интерактивных контролов окна/экрана с именами, типами и точными физическими координатами центров.
* 🔍 `desktop_find_text_ocr(query, window_title, lang)`: Поиск текста через встроенный движок Windows 11 `Windows.Media.Ocr` с возвратом точных координат рамки.

### 2. Захват экрана и окон без потери четкости (4K-Friendly Vision)
* 🪟 `desktop_take_window_screenshot(window_title)`: Захват конкретного окна в 100% оригинальном масштабе (1:1) без размытия мелких шрифтов и надписей.
* 🔍 `desktop_take_region_screenshot(x, y, width, height)`: Снимок произвольной области экрана 1:1 (экранная лупа).
* 📸 `desktop_take_screenshot(max_width)`: Полноэкранный обзорный снимок рабочего стола.

### 3. Мышь и клавиатура
* 🖱️ `desktop_mouse_click`, `desktop_mouse_move`, `desktop_mouse_drag`, `desktop_mouse_scroll`: Управление курсором мыши.
* ⌨️ `desktop_type_text`, `desktop_press_key`, `desktop_hotkey`: Полная поддержка ввода Unicode (русский, английский, спецсимволы) через Win32 `SendInput` и системные горячие клавиши.
* 🪟 `desktop_list_windows`, `desktop_focus_window`: Список открытых окон и переключение фокуса.
* 📏 `desktop_get_screen_info`: Разрешение дисплея и текущие координаты курсора.

## Особенности реализации
1. **Интерактивная сессия Windows:** использует ранний `OpenInputDesktop` и `SetThreadDesktop` для безошибочного захвата рабочего стола в фоновых процессах и сервисах.
2. **Нулевая задержка:** построен на легковесном официальном Python SDK `mcp.server.fastmcp`.
3. **Безопасность:** работает строго локально через стандартный stdio транспорт MCP.
