# OpenHands Nexus — Safe Update & Component Maintenance Suite

Централизованная экосистема безопасного аудита, верификации и обновления компонентов инженерной рабочей станции **OpenHands Nexus** на Windows 11.

---

## 1. Архитектурные принципы и политика безопасности

1. **Неприкосновенность ядра Upstream OpenHands:**
   - Кодовая база OpenHands не модифицируется напрямую. Все улучшения станции реализованы как неразрушающие оверлеи (патчеры, обратные прокси, профили, локализация).
2. **СТРОГАЯ ПОЛИТИКА ПО AI МОДЕЛЯМ (GGUF ВЕСА):**
   - **AI-модели (GGUF веса) строго исключены из автоматических обновлений.** Это самые тяжелые компоненты станции (~100+ ГБ суммарно), которые скачиваются и верифицируются вручную пользователем раз в полгода. Скрипты обновления только инспектируют целостность файлов моделей, но никогда не пытаются их автоматически перекачивать или перезаписывать.
3. **Безопасность по умолчанию (Safe Default -CheckOnly):**
   - Двойной клик на любой `.cmd` файл или запуск без параметров **никогда не выполняет деструктивных действий**. По умолчанию запускается режим `-CheckOnly`, выводящий матрицу версий и статус готовности.
4. **Изоляция и независимость компонентов (Decoupled Updates):**
   - Обновление каждого компонента изолировано и имеет собственные границы отката (rollback boundaries). Массовое автообновление "в один клик" отключено во избежание каскадных сбоев.
5. **Hard Safety Gate (Защита запущенных сервисов):**
   - Для модифицирующих операций с нативными LLM-бэкендами требуется предварительная остановка станции (`openhands stop`). Флаг `-Force` не может обойти проверку занятых портов.
6. **Автоматический откат и валидация:**
   - Перед любым обновлением создается снапшот в `Archive/backups/`. При ошибке квалификационного гейта (компиляция, замер токенов, тест UI или целостности словаря) автоматически восстанавливается предыдущая сборка.

---

## 2. Матрица 10 компонентов станции

| # | Компонент | Назначение | Текущая версия | Политика обновления | Инструмент обновления |
|---|:---|:---|:---|:---|:---|
| **1** | **llama-swap** | Маршрутизатор LLM моделей (Порт 8080) | `v255` | Релизы GitHub (x64 Windows) | `UPDATE-LLAMA-SWAP.cmd`<br>`update-llama-swap.ps1` |
| **2** | **ik_llama** | CUDA LLM бэкенд #1 (Qwen 3.8 27B / Ornith 35B / MTP) | `3c58ae3` | Зафиксирован на эталонной сборке (35.72 т/с MTP) | `UPDATE-IK-LLAMA.cmd`<br>`update-ik-llama.ps1` |
| **3** | **moe-expert-cache** | CUDA LLM бэкенд #2 (Qwen 3.5 122B MoE) | `bccbacd` | Сборка из ветки `moe-expert-cache` | `UPDATE-EXPERT-CACHE-BACKEND.cmd`<br>`update-expert-cache-backend.ps1` |
| **4** | **llama-mainline** | Официальный CUDA LLM бэкенд #3 (Standby) | `b10875` | Официальные precompiled релизы ggml-org | `UPDATE-LLAMA-MAINLINE.cmd`<br>`update-llama-mainline.ps1` |
| **5** | **@openhands/agent-canvas** | Веб-интерфейс рабочей станции (Порт 8000) | `v1.18.0` | Upstream npm registry + оверлей патчей | `UPDATE-OPENHANDS.cmd`<br>`update-openhands.ps1` |
| **6** | **openhands-agent-server** | Ядро выполнения агентов (Порт 18000) | `v1.46.0` | Зафиксировано в `defaults.json` Canvas (управляется Canvas через uvx) | Интегрировано в Agent Canvas |
| **7** | **openhands-automation** | Сервер автоматизации (Порт 18001) | `v1.11.1` | Зафиксировано в `defaults.json` Canvas (управляется Canvas через uvx) | Интегрировано в Agent Canvas |
| **8** | **local-voice** | Локальный голосовой мост STT/TTS (Порт 18002) | `v1.3.1` (GigaAM+Supertonic) | Python-зависимости (pip), модели зафиксированы | `UPDATE-VOICE-BRIDGE.cmd`<br>`update-voice-bridge.ps1` |
| **9** | **openhands-pwa** | LAN шлюз и PWA для планшета (Порт 8443) | mTLS SAN (1088 дней) | Мониторинг срока сертификата, автообновление при < 30 дн. | `UPDATE-PWA-GATEWAY.cmd`<br>`update-pwa-gateway.ps1` |
| **10** | **openhands-localization** | Русская локализация (2470 строк) | 100% паритет (0 missing) | Идемпотентный инжектор в бандл Canvas | Интегрировано в `update-openhands.ps1` |

---

## 3. Использование через единый CLI OpenHands

Главный диспетчер станции `openhands.ps1` поддерживает команду `update`:

```powershell
# Полная сводная таблица всех 10 компонентов станции:
openhands update

# Проверка конкретного компонента (Read-Only статус):
openhands update canvas -CheckOnly
openhands update swap -CheckOnly
openhands update voice -CheckOnly
openhands update pwa -CheckOnly
openhands update expert-cache -CheckOnly
openhands update mainline -CheckOnly
openhands update ik-llama -CheckOnly

# Симуляция обновления (DryRun):
openhands update canvas -DryRun
openhands update swap -DryRun

# Выполнение целевого обновления:
openhands update canvas
openhands update swap
openhands update voice
openhands update pwa
```

---

## 4. Запуск через графический интерфейс (Windows Explorer)

В корне каталога `K:\Project\OpenHands-Update\` находятся готовые `.cmd` лаунчеры для быстрого запуска по двойному клику:

| Лаунчер | Действие при двойном клике |
| :--- | :--- |
| `UPDATE-ALL.cmd` | Открывает общий дашборд матрицы 10 компонентов станции в режиме `-CheckOnly` |
| `UPDATE-OPENHANDS.cmd` | Проверяет и обновляет Agent Canvas v1.18.0 с автопатчем локализации и голоса |
| `UPDATE-LLAMA-SWAP.cmd` | Проверяет и обновляет бинарник роутера llama-swap |
| `UPDATE-IK-LLAMA.cmd` | Проверяет и обновляет эталонный бэкенд ik_llama (требует остановки станции) |
| `UPDATE-EXPERT-CACHE-BACKEND.cmd` | Проверяет и обновляет бэкенд MoE Expert Cache для Qwen 122B |
| `UPDATE-LLAMA-MAINLINE.cmd` | Проверяет и скачивает релиз официального llama.cpp (CUDA 12.4) |
| `UPDATE-VOICE-BRIDGE.cmd` | Проверяет Python-окружение голосового сервиса (GigaAM/Supertonic) |
| `UPDATE-PWA-GATEWAY.cmd` | Проверяет сертификаты mTLS, токен авторизации и брандмауэр для планшета |
| `ROLLBACK-OPENHANDS.cmd` | Выполняет мгновенный откат Agent Canvas к предыдущей резервной копии |
| `ROLLBACK-IK-LLAMA.cmd` | Выполняет мгновенный откат бинарника ik_llama к предыдущей сборке |

---

## 5. Структура каталогов

```
K:\Project\OpenHands-Update\
├── UPDATE-ALL.cmd                      # Главный лаунчер сводного дашборда
├── UPDATE-OPENHANDS.cmd                # Лаунчер обновления Agent Canvas
├── UPDATE-LLAMA-SWAP.cmd               # Лаунчер обновления llama-swap
├── UPDATE-IK-LLAMA.cmd                 # Лаунчер обновления ik_llama
├── UPDATE-EXPERT-CACHE-BACKEND.cmd     # Лаунчер обновления MoE Expert Cache
├── UPDATE-LLAMA-MAINLINE.cmd           # Лаунчер обновления mainline llama.cpp
├── UPDATE-VOICE-BRIDGE.cmd             # Лаунчер обновления Voice Bridge
├── UPDATE-PWA-GATEWAY.cmd              # Лаунчер проверки/обновления LAN PWA Gateway
├── ROLLBACK-OPENHANDS.cmd              # Быстрый откат Agent Canvas
├── ROLLBACK-IK-LLAMA.cmd               # Быстрый откат ik_llama
├── README.md                           # Данная документация
├── scripts\
│   ├── common.ps1                      # Общие утилиты, логгеры, проверки портов
│   ├── update-all.ps1                  # Сводный дашборд и диспетчер (-Component)
│   ├── update-openhands.ps1            # Скрипт обновления Agent Canvas + патчи
│   ├── rollback-openhands.ps1          # Скрипт отката Agent Canvas
│   ├── update-llama-swap.ps1           # Скрипт обновления роутера llama-swap
│   ├── update-ik-llama.ps1             # Скрипт сборки/обновления ik_llama
│   ├── rollback-ik-llama.ps1           # Скрипт отката ik_llama
│   ├── update-expert-cache-backend.ps1 # Скрипт обновления MoE Expert Cache
│   ├── update-llama-mainline.ps1       # Скрипт обновления официального llama.cpp
│   ├── update-voice-bridge.ps1         # Скрипт проверки/обновления Voice Bridge
│   └── update-pwa-gateway.ps1          # Скрипт проверки/ротации SSL certs PWA
└── state\
    └── last_run_status.json            # JSON-состояние последних запусков
```

---

## 6. Журналирование и аудит

Все операции логируются в централизованный каталог станции:
`K:\Project\Logs\Updater\`

Каждый запуск создает файл с временной меткой:
- `update-all-YYYYMMDD-HHmmss.log`
- `update-openhands-YYYYMMDD-HHmmss.log`
- `update-voice-bridge-YYYYMMDD-HHmmss.log`
- `update-pwa-gateway-YYYYMMDD-HHmmss.log`
- `update-expert-cache-YYYYMMDD-HHmmss.log`
- `update-llama-mainline-YYYYMMDD-HHmmss.log`
- `update-llama-swap-YYYYMMDD-HHmmss.log`
- `update-ik-llama-YYYYMMDD-HHmmss.log`
