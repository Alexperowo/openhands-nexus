# OPENHANDS NEXUS — ДОРОЖНАЯ КАРТА

> **Финальная цель проекта:**  
> OpenHands Nexus = стабильный локальный AI Remote Control для Windows 11, которым можно управлять с компьютера и Android (планшет/смартфон) без технической настройки моделей, с Working Profiles, Team-Full, голосом, PWA, accessibility, обновлением и возможностью переноса на другой ПК.

---

## Матрица этапов и текущий статус

| Этап | Название | Статус | Прогресс | Ключевые компоненты |
|:---|:---|:---:|:---:|:---|
| **Этап 0** | Базовая точка (Checkpoint & Baseline) | ✅ | 100% | Archive/backups, Baseline inventory, Rollback point |
| **Этап 1** | Working Profiles (Система профилей) | ✅ | 100% | Config/working-profile-templates, working_profiles.py |
| **Этап 2** | Remote Control UI (Единый интерфейс) | ✅ | 100% | working-profile-ui.js/css, LAN Gateway (:8443) |
| **Этап 3** | Reasoning / Thinking (Режимы рассуждений) | ✅ | 100% | Dynamic reasoning selector, model capabilities sync |
| **Этап 4** | Voice + Accessibility + UI Polish | ✅ | 100% | local-voice (STT, Dual TTS), WCAG 2.5.5/2.4.7, UI Sprints 1-4 |
| **Этап 5** | Physical Android E2E (Samsung Tab S9 Ultra) | 🟡 | 60% | Wi-Fi ADB (192.168.0.34:5555), PWA, Live test suite |
| **Этап 6** | Team-Full / Agent Runtime | ⏳ | 40% | llama-swap, 3-model chain, Tool Calling, VRAM control |
| **Этап 7** | Update Hardening | ⏳ | 50% | Idempotent patchers, custom layer decoupling |
| **Этап 8** | Portable Release / Recovery | ⏳ | 30% | Derived paths (K:\Project, %USERPROFILE%), portable setup |
| **Этап 9** | Final Release & QA Sign-off | ⏳ | 15% | Full regression, clean docs, release archive |

---

## Подробное описание этапов

### Этап 0 — Базовая точка
- [x] Полный бэкап проекта
- [x] Контрольная точка для отката (Baseline Checkpoint)
- [x] Инвентаризация компонентов системы
- **Статус:** ✅ **Завершён**

### Этап 1 — Working Profiles
- [x] Единая система «Рабочих профилей» (7 шаблонов в Config/working-profile-templates/)
- [x] Поддержка одиночных моделей и командных связок (1 / 2 / 3 модели)
- [x] Серверное хранение состояния в %USERPROFILE%\.openhands\working_profile_state.json
- [x] Сохранение выбранного профиля между перезапусками
- [x] Изоляция профиля текущей задачи (блокировка на время выполнения шага isTaskRunning())
- **Статус:** ✅ **Завершён**

### Этап 2 — Remote Control UI
- [x] Единый интерфейс Desktop + Android
- [x] Выбор Working Profile прямо над композером ввода
- [x] Двусторонняя синхронизация между карточкой профиля и селектором OpenHands
- [x] Удобный интерфейс управления OpenHands без технического мусора
- **Статус:** ✅ **Завершён**

### Этап 3 — Reasoning / Thinking
- [x] Direct / Low / Medium / High для Qwen 3.8 Opus
- [x] Normal / Deep для Qwen3-Next
- [x] Стандартная команда / Глубокая команда для Team-Full
- [x] Только реально поддерживаемые режимы (Ornith Coder в фиксированном режиме без лишних селекторов)
- **Статус:** ✅ **Завершён**

### Этап 4 — Voice + Accessibility + UI
- [x] STT (локальный FastConformer/Whisper через port 18002)
- [x] Android Native TTS (Samsung TTS на мобильных)
- [x] Supertonic TTS (локальный серверный TTS)
- [x] Ручная озвучка ответа (кнопка динамика у каждого сообщения ассистента)
- [x] Auto-TTS (автоматическое воспроизведение новых ответов)
- [x] Stop / Barge-in (прерывание речи при новом вводе или нажатии Стоп)
- [x] TalkBack / ARIA (ARIA-live polite announcer oh-wp-status-announcer)
- [x] Крупные touch controls (WCAG 2.5.5 / 2.5.8 ≥44-48px)
- [x] Нормальный мобильный интерфейс (mobile-pwa.css, safe-area insets, 100dvh)
- [x] Финальная полировка Remote Control UI (Sprints 1–4: компактная карточка, авто-затухание пилюли, кольца фокуса)
- **Статус:** ✅ **Завершён**

### Этап 5 — Physical Android E2E
- [x] Полный сценарий на реальном Samsung Galaxy Tab S9 Ultra (192.168.0.34:5555)
- [x] Создание новой задачи с планшета
- [x] Выбор профиля на планшете с мгновенным отражением на ПК
- [x] Выбор глубины Reasoning (Direct / Low / Medium / High)
- [x] Отправка задания
- [x] Получение ответа агента
- [x] Голосовой ввод STT (FUTO GigaAM v3) → ChatInput → отправка
- [x] Manual TTS (кнопка 🔊 у каждого сообщения) и Auto-TTS (Samsung Native / Supertonic)
- [x] Прерывание Stop / Barge-in
- [x] Поведение клавиатуры и скроллинга (visualViewport, 100dvh, safe-area insets)
- [x] Двусторонняя синхронизация Desktop ↔ Android (Visibility Polling 3s, server persistence)
- **Статус:** ✅ **Завершён**

### Этап 6 — Team-Full / Agent Runtime (ТЕКУЩИЙ)
- [ ] Полная сквозная проверка цепочки Team-Full
- [ ] Командный цикл: Qwen (Архитектор) → Ornith (Кодер) → Next (Ревьюер)
- [ ] Реальное выполнение агентных задач (создание файлов, правка кода, выполнение команд)
- [ ] Tool calling в локальном инференсе
- [ ] Model switching / lifecycle в llama-swap
- [ ] MTP (Multi-Token Prediction) валидация
- [ ] Контроль потребления VRAM при переключениях (бюджет 22 GB RTX 2080 Ti)
- [ ] Обработка ошибок и авто-восстановление
- **Статус:** 🟡 **В работе**

### Этап 7 — Update Hardening
- [ ] Процедура обновления OpenHands
- [ ] Процедура обновления Agent Canvas
- [ ] Обновление llama.cpp / ik_llama
- [ ] Обновление llama-swap
- [ ] Повторное автоматическое применение custom layer
- [ ] Идемпотентные патчеры (patch-agent-canvas-working-profile.ps1, patch-agent-canvas-voice.ps1, patch-agent-canvas-pwa.ps1)
- [ ] Механизм отката (Rollback)
- [ ] Сохранение Working Profiles / Voice / PWA / Localization после апдейтов
- **Статус:** ⏳ **Запланирован**

### Этап 8 — Portable Release / Recovery
- [ ] Чистая установка из архива
- [ ] Первый запуск «из коробки»
- [ ] Автоматическая первичная конфигурация
- [ ] Перенос на другой Windows 11 PC без правок путей
- [ ] Восстановление после сбоя
- [ ] Скрипты Backup / Restore
- [ ] Проверка всех системных зависимостей
- [ ] 100% отсутствие machine-specific hardcoded paths
- **Статус:** ⏳ **Запланирован**

### Этап 9 — Final Release
- [ ] Финальный аудит кода и безопасности
- [ ] Очистка временных файлов и логов
- [ ] Актуализация всей документации
- [ ] Полная верификация GitHub (Alexperowo/openhands-nexus)
- [ ] Финальный сквозной regression test:
  - Desktop + Android
  - Voice + PWA
  - Models + Team-Full
  - Update + Recovery
- [ ] Создание релизного архива (Release Archive)
- **Статус:** ⏳ **Запланирован**
