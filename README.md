# OpenHands-Nexus для Linux

Локальный автономный агент на базе [OpenHands Agent Canvas](https://www.npmjs.com/package/@openhands/agent-canvas)
с доступностью для слабовидящего пользователя: крупный русский интерфейс, озвучка ответов,
голосовой ввод, звуковые сигналы и управление с планшета (Chrome PWA по HTTPS в домашней сети).

Ядро OpenHands не меняется: это npm-пакет точной версии. Всё своё — надстройка рядом с ним.
Ветка `master` — прежняя версия для Windows.

## Устройство

| Папка | Что это | Служба, порт |
|---|---|---|
| `agent/` | Agent Canvas как зависимость (agent-server, automation); состояние в `agent/state/`, настройки агента и LLM-профили в `agent/config/` | `ohn-agent`: 8010, 18010, 18011 |
| `ui/` | Надстройка: React-хост компонентов Canvas, русская локаль, озвучка, диктовка, переключатель моделей | статика через шлюз |
| `voice/` | Распознавание GigaAM v3 и синтез Silero v5.6 (CPU), OpenAI-совместимые `/v1/audio/*` | `ohn-voice`: 18020 |
| `models/` | Меню моделей: [llama-swap](https://github.com/mostlygeek/llama-swap) поверх ik_llama `llama-server` | `ohn-models`: 18030, модели 18040+ |
| `gateway/` | Caddy: HTTPS для планшета, сам подставляет ключ сессии в `/api` и `/sockets` | `ohn-gateway`: 8443 |
| `screen/` | Команды экрана для агента: `desk` от H Company ([hai-drivers](https://pypi.org/project/hai-drivers/), MIT; на них обучена Holo4) — снимок, клик, клавиши, текст, окна; координаты 0–1000 | в терминале агента |
| `guard/` | Страж опасных команд агента (PreToolUse-хук в каждой беседе, в том числе в задачах по расписанию): не даёт убить Nexus, сеанс или систему, менять сеть; личные папки целиком — только в корзину | — |
| `launcher/` | `run.sh` для user-юнитов systemd, ярлыки «Запустить/Остановить Nexus», `install.sh` | — |
| `update/` | `nexus-update`: проверка и обновление Canvas, ik_llama, llama-swap, Caddy, голосовых пакетов с откатом | — |

Службы работают прямо из этого клона. Ключи — в `~/.config/openhands-nexus/session.env` (0600),
вне репозитория. Автозапуска нет намеренно: видеокарты делятся с другими задачами.

Рабочая папка бесед — `~/Nexus` (создаётся сама; agent-server заводит в ней git для вкладки изменений).

Страницы Canvas для навыков, задач по расписанию и расширений надстройка не показывает:
задачи по расписанию работают (служба automation, порт 18011), но создаются и смотрятся только через API.

## Установка

Нужны: Linux с systemd (user-сеанс), Node 24, [uv](https://docs.astral.sh/uv/), Python 3.12,
системный `libflite1` (произношение латиницы), сборка
[ik_llama.cpp](https://github.com/ikawrakow/ik_llama.cpp) с CUDA.

```bash
(cd agent && npm ci)
(cd ui && npm ci && npm run build)
(cd voice && uv sync --frozen && .venv/bin/python download_models.py)
(cd screen && uv sync --frozen)   # нужны системные xdotool, wmctrl, xclip
```

Бинарники не хранятся в git: положить `caddy` в `gateway/`, `llama-swap` в `models/`.
В `models/llama-swap.yaml` указать путь к `llama-server` и к весам моделей.
Шлюзу нужен корневой сертификат `gateway/ca/openhands-ca.{crt,key}`; планшет доверяет ему,
файл для установки отдаётся по `http://<адрес ПК>:8081/ca.crt`.

```bash
launcher/install.sh   # ключи сессии (один раз), юниты ohn-*, ярлыки на рабочем столе
```

## Запуск

Ярлык «Запустить Nexus» (или `systemctl --user start ohn.target`) поднимает модель, голос, агента
и шлюз и сообщает о готовности голосом и уведомлением. Планшет: `https://<адрес ПК>:8443/`.
«Остановить Nexus» выгружает модель и освобождает видеокарты.

## Модели

Меню llama-swap держит одну модель за раз. В Canvas каждой модели соответствует LLM-профиль
(`openai/<id из llama-swap.yaml>`, адрес `http://127.0.0.1:18030/v1`, свой `max_input_tokens`);
переключатель под строкой ввода меняет модель беседы на ходу. Профили, подсказка агента
(`agent/config/suffix.md`) и прочие отличия от настроек OpenHands по умолчанию хранятся в git:

```bash
python3 -I agent/config.py check   # что на сервере агента разошлось с git (без значений)
python3 -I agent/config.py apply   # записать профили и настройки, включить активный профиль
```

Профиль дополняет общую часть `profiles.json`, вложенные объекты сливаются по ключам. Выборка —
по карточкам моделей: Nex N2.5 — 0.7 / top_p 0.95 / top_k 40, Tess и Holo4 (Qwen3.8) —
1.0 / 0.95 / 20, min_p 0. `send_reasoning_content` в `capability_overrides` возвращает модели её
прошлые размышления: Tess (карточка: preserve_thinking в агентных циклах) и Nex (шаблон всегда
их выводит) — да, Holo4 — нет (её harness их не повторяет). agent-server 1.58 этот ключ не
читает: до релиза с PR OpenHands/software-agent-sdk#4446 его учитывает `agent/sdk-patch`.
Там же исправлен подсчёт токенов после смены модели или уровня рассуждений (иначе индикатор
контекста пишет «данных пока нет»; #5639). Зациклившееся размышление (длинная фраза 3+ раза)
уходит модели без повторов — иначе она продолжала петлю в следующих шагах; в беседе хранится
оригинал. На бюджете размышления (`thinking_budget_tokens`) сервер завершает мысль фразой
`budget_message` из `llama-swap.yaml`, а не обрывает её на полуслове.

Сжатие беседы начинается с 70% окна модели (`max_input_tokens` профиля; потолок 160000 —
`condenser` в `settings.json`): ранние шаги заменяет журнал шагов, собранный без обращения к модели.
Свежие из них — с аргументами и выжимкой результата, старые — строкой; сообщения пользователя
и отказы стража — дословно; журнал прошлого сжатия сворачивается в строки
(`agent/sdk-patch/nexus_ledger.py`). Резюме самой моделью остаётся на пределе контекста
и на случай, если журнал перерос четверть порога.

Экран агент видит и трогает командами из `screen/bin` (`screenshot`, `click`, `key`, `text`,
`focus`…; описание — `desk skill`). Строка `@@attach <картинка>` в их выводе становится
изображением в результате команды, как в обвязке, на которой обучена Holo4: до 1920 px, JPEG 85
(`agent/sdk-patch/nexus_screen.py`).

## Проверки

```bash
(cd ui && for t in test-logic test-providers test-stream test-smooth test-backend-origin test-stream-ui test-smooth-ui; do node $t.mjs || break; done)  # *-ui: Firefox, Chrome
(cd guard && python3 test_guard.py)
(cd voice && .venv/bin/python test_pronunciation.py)
(cd update && python3 test_update.py)
update/nexus-update check
python3 -I agent/config.py check
```

Стенд интерфейса без настоящих служб — `ui/dev/README.md`.
