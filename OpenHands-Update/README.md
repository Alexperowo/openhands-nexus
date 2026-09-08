# OpenHands Local & ik_llama Safe Updater Suite

Инструменты безопасного ручного обновления компонентов платформы OpenHands Local:
1. **OpenHands Agent Canvas** (Frontend SPA + Agent/Automation servers)
2. **ik_llama backend** (CUDA-ускоренный LLM-сервер для Qwen 3.8 27B Opus на RTX 2080 Ti)

---

## Архитектурные принципы

- **Безопасность (Staging First):** обновление никогда не перезаписывает рабочий runtime напрямую. Новая сборка проверяется в изолированном окружении/staging.
- **Отказоустойчивость (Automatic Rollback):** при любой ошибке (несовместимость патчей, падение smoke-теста, деградация скорости, новые непереведённые ключи) рабочая версия восстанавливается автоматически.
- **Соблюдение прав владения процессами (Ownership):** скрипты никогда не убивают процессы по имени или случайному совпадению портов. Используется схема сессий и PID-родословной (`session.json`).
- **Сохранение локализации:** при появлении новых английских ключей в upstream-пакете обновление отклоняется с причиной `LOCALIZATION_UPDATE_REQUIRED` для предотвращения порчи русского словаря.
- **Секретная гигиена:** логи не содержат API-токенов или секретных ключей.

---

## Доступные лаунчеры

| Лаунчер | Назначение | Поведение |
| :--- | :--- | :--- |
| `UPDATE-OPENHANDS.cmd` | Обновление Agent Canvas | Проверяет npm registry. Если нет обновления — `NO_UPDATE_AVAILABLE`. Бэкапит текущую версию, обновляет, накатывает патчи локализации и голоса, проверяет 2400 ключей, проводит smoke-тест. |
| `UPDATE-IK-LLAMA.cmd` | Обновление ik_llama backend | Проверяет git commit. Собирает Release с CUDA sm_75 в `build-staging`. Тестирует на порту 18080: загрузка 96K, MTP, chat completion, замер tok/s. Только при PASS заменяет `bin/`. |
| `UPDATE-ALL.cmd` | Полное последовательное обновление | Сначала обновляет ik_llama. При ошибке прерывает работу. При успехе обновляет OpenHands. |
| `ROLLBACK-OPENHANDS.cmd` | Откат OpenHands | Восстанавливает последнюю резервную копию из `backups/openhands/`, перезапускает платформу и валидирует. |
| `ROLLBACK-IK-LLAMA.cmd` | Откат ik_llama | Восстанавливает предыдущую сборку из `backups/ik_llama/`, перезапускает и валидирует порт 8080. |

---

## Структура каталогов

```
K:\Project\OpenHands-Update\
├── UPDATE-OPENHANDS.cmd
├── UPDATE-IK-LLAMA.cmd
├── UPDATE-ALL.cmd
├── ROLLBACK-OPENHANDS.cmd
├── ROLLBACK-IK-LLAMA.cmd
├── README.md
├── scripts\
│   ├── common.ps1
│   ├── update-openhands.ps1
│   ├── rollback-openhands.ps1
│   ├── update-ik-llama.ps1
│   ├── rollback-ik-llama.ps1
│   └── update-all.ps1
├── logs\
└── backups\
    ├── openhands\
    └── ik_llama\
```
