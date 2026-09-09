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
| **Этап 5** | Physical Android E2E (Samsung Tab S9 Ultra) | ✅ | 100% | Wi-Fi ADB (192.168.0.34:5555), PWA, Live test suite |
| **Этап 6** | Team-Full / Agent Runtime | ✅ | 100% | llama-swap, 3-model chain, Tool Calling, VRAM control |
| **Этап 7** | Update Hardening | ✅ | 100% | Idempotent patchers, custom layer decoupling |
| **Этап 8** | Portable Release / Recovery | ✅ | 100% | Derived paths, check-dependencies, setup, backup, restore, recover |
| **Этап 9** | Final Release & QA Sign-off | ✅ | 100% | Security audit, clean docs, end-to-end regression validation, QA Sign-off |

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

### Этап 6 — Team-Full / Agent Runtime
- [x] Полная сквозная проверка цепочки Team-Full (Qwen3.8 Opus + Ornith 1.5 Coder + Qwen3-Next 80B Thinking)
- [x] Командный цикл: Qwen (Архитектор / План) → Ornith (Кодер / Тесты) → Next (Ревьюер / Deep Debug)
- [x] Реальное выполнение агентных задач (создание файлов, правка кода, выполнение команд, pytest)
- [x] Tool calling в локальном инференсе (switch_llm, terminal, file_editor, task_tracker, finish)
- [x] Model switching / lifecycle в llama-swap (unloadTimeout 15s, cmdStop force kill, 3s VMM buffer)
- [x] MTP (Multi-Token Prediction) валидация (Qwen 21 t/s, Ornith 63 t/s, Next draft MTP ~20 t/s)
- [x] Контроль потребления VRAM при переключениях (бюджет 22 GB RTX 2080 Ti; Qwen 21.9 GB, Ornith 20.4 GB, Next 21.5 GB; сброс до 737 MB)
- [x] Обработка ошибок и авто-восстановление (Routing policy: 2 failed normal cycles → Next escalation)
- **Статус:** ✅ **Завершён**

### Этап 7 — Update Hardening
- [x] Процедура обновления OpenHands (update-openhands.ps1 -CheckOnly, -DryRun, -Update)
- [x] Процедура обновления Agent Canvas (npm install, backup, defaults.json pins, smoke test)
- [x] Обновление llama.cpp / ik_llama (update-ik-llama.ps1 -CheckOnly, -DryRun, -Update)
- [x] Обновление llama-swap (update-llama-swap.ps1 -CheckOnly, -DryRun, -Update)
- [x] Повторное автоматическое применение custom layer (Localization, Voice, Working Profiles, PWA)
- [x] Идемпотентные патчеры (patch-agent-canvas-working-profile.ps1, patch-agent-canvas-voice.ps1, patch-agent-canvas-pwa.ps1, patch-agent-canvas-localization.ps1, patch-agent-canvas-local-llm.ps1)
- [x] Механизм отката (Rollback: rollback-openhands.ps1, rollback-ik-llama.ps1)
- [x] Сохранение Working Profiles / Voice / PWA / Localization после апдейтов (2400 ключей, strict parity gate, smoke tests)
- **Статус:** ✅ **Завершён**

### Этап 8 — Portable Release / Recovery
- [x] Чистая установка из архива
- [x] Первый запуск «из коробки» (SETUP-OPENHANDS-LOCAL.cmd -> setup.ps1)
- [x] Автоматическая первичная конфигурация (семена профилей, шаблоны, SSL certs, firewall)
- [x] Перенос на другой Windows 11 PC без правок путей (динамические пути %~dp0, $ProjectRootDir)
- [x] Восстановление после сбоя (RECOVER-OPENHANDS-LOCAL.cmd -> recover.ps1)
- [x] Скрипты Backup / Restore (BACKUP-OPENHANDS.cmd, RESTORE-OPENHANDS.cmd)
- [x] Проверка всех системных зависимостей (CHECK-DEPENDENCIES.cmd - 34/34 пройдены)
- [x] 100% отсутствие machine-specific hardcoded paths
- **Статус:** ✅ **Завершён**

### Этап 9 — Final Release & QA Sign-off
- [x] Финальный аудит кода и безопасности (санитизация токенов, ключей, secrets)
- [x] Очистка временных файлов и логов
- [x] Актуализация всей документации (README.md, архитектура, запуск на чистом ПК)
- [x] Финальный сквозной regression test (21/21 тестов пройдено со 100% успехом):
  - Desktop + Android PWA (Samsung Galaxy Tab S9 Ultra 192.168.0.34:5555)
  - Voice STT (GigaAM v3) + TTS (Supertonic 3 / Samsung)
  - Models + Team-Full (Qwen 3.8 + Ornith 1.5 + Qwen3-Next 80B)
  - Update + Backup / Recovery (backup-station.ps1, recover.ps1)
- [x] Полная верификация GitHub (Alexperowo/openhands-nexus)
- [x] Финальный отчет с QA Sign-off
- **Статус:** ✅ **Завершён**
