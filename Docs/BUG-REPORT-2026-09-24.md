# Баг-репорт: Живое тестирование OpenHands Nexus — 24 сентября 2026

> Выявлено при живом end-to-end тестировании на Samsung Galaxy Tab S9 Ultra через LAN PWA.
> Конвертация `ad414602-8a54-4f88-aa8fce257faeef90` (403 события).

---

## 🔴 Критические (блокирующие работу)

### BUG-01: Qwen 122B — полностью сломана генерация на русском языке
- **Симптом:** Модель отвечает ломаным миксом русского, английского и китайского. «Хороо, ИOpenHands agent, саво ИAssistant». При системном промпте «отвечай по-русски» думает на английском, затем проваливается в мандаринский (中文).
- **Причина:** Expert pruning (256→208) с англоязычным калибровочным датасетом убил мультиязычных экспертов.
- **Решение:** Перепрунить с мультиязычным калибровочным датасетом (русский + английский).
- **Workaround:** Использовать Qwen 27B для русскоязычных задач.
- **Файл:** [TODO-recalibrate-qwen122-russian.md](file:///K:/Project/Docs/TODO-recalibrate-qwen122-russian.md)

### BUG-02: Контекст исчерпывается — модель уходит в stuck
- **Симптом:** После ~170 событий (ConversationStateUpdateEvent) диалог переполнил контекст. Сработал CondensationRequest (event-172), но к финалу диалога (event-401) агент завис в статусе `stuck`. Последний ответ — пустой content. Система выдала: «Your last response did not include a function call or a message».
- **Данные:** 1 279 719 prompt_tokens, 3 990 completion_tokens, 1 220 476 cache_read_tokens. Condensation сработала один раз, но не спасла.
- **Причина:** Condensation сжала только ранние события, но каждый шаг agent loop генерирует ConversationStateUpdateEvent (stats), раздувая контекст дальше.
- **Решение:** Проверить настройки condensation в OpenHands — порог, частоту, стратегию. Возможно, нужна агрессивная condensation или ограничение stats-событий.

### BUG-03: Терминал PowerShell умирает посреди диалога
- **Симптом:** Агент пытается выполнить команду → «Error executing tool 'terminal': Cannot send keys: PowerShell process is not running» (events 283, 285).
- **Причина:** PowerShell-процесс агента завершился (crash или timeout), а OpenHands не перезапустил его.
- **Решение:** Проверить настройки timeout и keepalive для терминального процесса в OpenHands agent server.

---

## 🟠 Серьёзные (влияют на функциональность)

### BUG-04: Vision/проектор подключён, но недоступен агенту
- **Симптом:** В llama-swap для Qwen 27B загружен `--mmproj` (мультимодальный проектор), но у агента нет инструмента `inspect_image_with_vision`. Модель физически умеет видеть, но OpenHands не предоставляет маршрут к этой возможности.
- **Причина:** Agent profile для Qwen 27B не включает vision capability и не маршрутизирует image-контент через OpenAI-совместимый multimodal endpoint.
- **Решение:** Добавить `vision: true` в capability_overrides LLM-профиля и/или настроить маршрутизацию image_url через llama-swap.

### BUG-05: TTS обрывается на английских словах
- **Симптом:** Озвучивание ответа прерывается, когда в русском тексте встречается английское слово.
- **Причина:** GigaAM TTS обучен на русском, переключение языка вызывает ошибку или молчаливый сбой в пайплайне синтеза.
- **Решение:** Проверить voice-bridge.js / service.py — как обрабатывается переключение языка. Возможно, нужна транслитерация английских слов перед синтезом, или fallback на skip.

### BUG-06: mobile-pwa.css — плашка «Размышление» не скрылась
- **Симптом:** После коммита CSS-правила `display:none` для `[data-testid="collapsible-thinking"]` плашка по-прежнему видна.
- **Причина:** LAN Gateway (`lan-gateway.mjs`) кэширует статику в `staticCache = new Map()` при первом запросе. Файл обновлён на диске, но gateway отдаёт старую версию из памяти.
- **Решение:** Перезапустить LAN Gateway. Или добавить cache-busting (версионирование query string) или убрать in-memory кэш для dev-файлов.

### BUG-07: Панель управления голосом не перетаскивается
- **Симптом:** Голосовой элемент управления перестал перемещаться на мобильном экране.
- **Причина:** Не определена — в `voice-bridge.js` и `voice-bridge.css` нет кода drag/touch. Возможно, это функциональность upstream Agent Canvas или конфликт с CSS `touch-action: manipulation` из mobile-pwa.css.
- **Решение:** Исследовать, был ли drag у voice pill раньше и что его сломало.

---

## 🟡 Средние (работает, но неудобно)

### BUG-08: Pydantic validation errors при создании диалога
- **Симптом:** Лог agent-server содержит серию `literal_error` от Pydantic при POST /api/conversations (08:31:49). Множество ошибок `type=literal_error`.
- **Причина:** Некорректный формат запроса от UI или несовместимость версий API schema.
- **Решение:** Проверить, какие поля вызывают literal_error — вероятно, расхождение между agent-canvas и agent-server.

### BUG-09: Git «dubious ownership» для public-skills
- **Симптом:** `fatal: detected dubious ownership in repository at 'C:/Users/User/.openhands/cache/skills/public-skills'`. Повторяется 6 раз в логах.
- **Причина:** Репозиторий создан другим пользователем (или от другого процесса), Windows git ругается на ownership.
- **Решение:** `git config --global --add safe.directory C:/Users/User/.openhands/cache/skills/public-skills`

### BUG-10: Chromium preload error
- **Симптом:** «Error preloading chromium» при старте agent-server.
- **Причина:** Chromium (для browser tool) не установлен или путь неверный.
- **Решение:** Установить playwright chromium или настроить путь.

### BUG-11: OCR не работает — модель не может прочитать текст со скриншота
- **Симптом:** Агент потратил ~20 шагов пытаясь OCR-ить скриншот: Tesseract не установлен, Windows OCR API не работает, ручное увеличение не помогло. «Текст на скриншоте слишком мелкий для OCR... похоже, в терминале используется шрифт с китайскими иероглифами» (на самом деле — обычный терминал).
- **Причина:** Нет установленного Tesseract, нет рабочего OCR-инструмента, vision-проектор не подключён (см. BUG-04).
- **Решение:** Либо подключить vision (BUG-04), либо установить Tesseract с русским языковым пакетом.

---

## 📊 Статистика диалога

| Метрика | Значение |
|---------|----------|
| Всего событий | 403 |
| Prompt tokens | 1 279 719 |
| Completion tokens | 3 990 |
| Cache read tokens | 1 220 476 |
| Condensation events | 1 (event-172) |
| Ошибки терминала | 2 (events 283, 285) |
| Финальный статус | `stuck` |
| Модель | openai/qwen122-turbo |
