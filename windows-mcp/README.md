# windows-mcp

> **MCP-сервер для автономного управления рабочим столом Windows (Computer Use)**

Позволяет локальным ИИ-агентам (OpenHands, Claude Desktop, Antigravity) полноценно управлять компьютером на Windows:
* 📸 `desktop_take_screenshot`: создание скриншотов экрана (с автоматическим пропорциональным сжатием до безопасного Full HD).
* 🖱️ `desktop_mouse_click`, `desktop_mouse_move`, `desktop_mouse_drag`, `desktop_mouse_scroll`: управление курсором мыши.
* ⌨️ `desktop_type_text`, `desktop_press_key`, `desktop_hotkey`: набор текста и комбинации клавиш.
* 🪟 `desktop_list_windows`, `desktop_focus_window`: перечисление и переключение окон по заголовкам.
* 📏 `desktop_get_screen_info`: геометрия дисплея и положение курсора.

## Особенности реализации
1. **Интерактивная сессия Windows:** использует `OpenInputDesktop` и `SetThreadDesktop` для безошибочного захвата рабочего стола в любых сценариях и фоновых процессах.
2. **Нулевая задержка:** построен на легковесном официальном Python SDK `mcp.server.fastmcp`.
3. **Безопасность:** работает строго локально через стандартный stdio транспорт MCP.
