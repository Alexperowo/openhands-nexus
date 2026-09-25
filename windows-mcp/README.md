# windows-mcp

> **MCP-сервер для автономного управления рабочим столом Windows и браузером (Computer Use) с поддержкой 4K-дисплеев**

Позволяет локальным ИИ-агентам (OpenHands Nexus, Claude Desktop, Antigravity) полноценно управлять компьютером на Windows, включая текстовые модели (Next 80B, Qwen 122B) и мультимодальные модели (Qwen 27B, Ornith 35B). Включает 27 специализированных инструментов:

### 1. Браузерная автоматизация (Playwright / Chrome DevTools Protocol) — 100% точность на 4K
* 🌐 `browser_open(url, headless, cdp_port)`: Запуск Chrome или подключение к уже работающему браузеру.
* 🖱️ `browser_click(selector, timeout_ms)`: Клик по CSS-селекторам, текстовым маркерам (`text=...`) или ARIA-ролям через DOM.
* ⌨️ `browser_type(selector, text, clear_first)`: Заполнение полей ввода, форм и редакторов кода.
* ⌨️ `browser_press_key(key)`: Нажатие клавиш в активной вкладке (`Enter`, `Control+Enter`, `Tab`).
* 📖 `browser_get_content(selector, max_length)`: Чтение текстового содержимого элементов или всей страницы в реальном времени.
* ⏳ `browser_wait_for(selector, timeout_ms, state)`: Детерминированное ожидание появления/скрытия элементов.
* ⚡ `browser_evaluate(script)`: Выполнение произвольного JavaScript-кода в контексте страницы.
* 📸 `browser_take_screenshot(max_width)`: Высокоточный снимок вкладки без искажений масштабирования Windows.
* 🚪 `browser_close()`: Корректное закрытие браузера и освобождение памяти.

### 2. Системная навигация Windows (UI Automation & WinRT OCR)
* 🎯 `desktop_click_element(name, window_title)`: Умный клик по названию элемента («Пуск», «Старт», ярлыки, кнопки, табы) через UIA с OCR-фолбэком.
* ⚡ `desktop_invoke_element(name, window_title)`: Вызов действия кнопки/меню через UIA InvokePattern напрямую в ОС без движения курсора.
* ✏️ `desktop_set_element_text(name, text, window_title)`: Прямая запись текста в системные поля ввода через UIA ValuePattern (без сбоев раскладки).
* 📋 `desktop_list_elements(window_title, max_elements)`: Полный список интерактивных контролов окна с именами и точными координатами центров.
* 🔍 `desktop_find_text_ocr(query, window_title, lang)`: Поиск текста на экране через аппаратный OCR-движок Windows 11 `Windows.Media.Ocr`.

### 3. Захват экрана и окон без потери четкости (4K-Friendly Vision)
* 🪟 `desktop_take_window_screenshot(window_title)`: Захват конкретного окна в 100% оригинальном масштабе (1:1).
* 🔍 `desktop_take_region_screenshot(x, y, width, height)`: Снимок произвольной области экрана 1:1 (экранная лупа).
* 📸 `desktop_take_screenshot(max_width)`: Полноэкранный обзорный снимок рабочего стола.

### 4. Низкоуровневое управление мышью и клавиатурой
* 🖱️ `desktop_mouse_click`, `desktop_mouse_move`, `desktop_mouse_drag`, `desktop_mouse_scroll`: Управление курсором мыши.
* ⌨️ `desktop_type_text`, `desktop_press_key`, `desktop_hotkey`: Ввод Unicode (русский, английский, символы) через Win32 `SendInput` и системные шорткаты.
* 🪟 `desktop_list_windows`, `desktop_focus_window`: Список открытых окон и переключение фокуса.
* 📏 `desktop_get_screen_info`: Разрешение дисплея и текущие координаты курсора.

## Архитектура и надежность
1. **Интерактивная сессия Windows:** использует `OpenInputDesktop` и `SetThreadDesktop` для безошибочного захвата рабочего стола в фоновых процессах и сервисах.
2. **Нулевая задержка:** построен на легковесном официальном Python SDK `mcp.server.fastmcp`.
3. **Безопасность:** работает строго локально через стандартный stdio транспорт MCP без сторонних внешних облачных зависимостей.
