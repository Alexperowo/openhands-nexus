# Обновление движков Nexus на Linux

Точка входа — `./nexus-update`, Bash с `set -euo pipefail`; реализация —
`nexus_update.py`, только стандартная библиотека Python 3.11+.
Дерево вычисляется относительно скрипта, backend — `~/backend/ik_llama-fresh`.
Без аргументов выполняется **только check**. Sudo не используется.

| Команда | Действие |
|---|---|
| `./nexus-update [check]` | Установленные/доступные версии: npm, pins из tarball, git ls-remote и отставание, GitHub releases Caddy, uv resolver dry-run. Проекты/окружения не меняются; допустимы журнал и кэши инструментов |
| `./nexus-update check --offline` | Без сети; доступные версии — unknown |
| `./nexus-update canvas [VERSION]` | Точная одинаковая версия в двух проектах, build overlay, отчёт локали, restart agent → gateway, health и API smoke guard. При ошибке восстановление обоих проектов, build, restart и health |
| `./nexus-update ik-llama [COMMIT]` | По умолчанию origin/main; проверки занятости, диска и чистоты tracked-файлов, новый каталог сборки, --version до/после swap. Сохраняет build.prev; службу модели не запускает |
| `./nexus-update ik-llama [COMMIT] --bench /path/model.gguf` | Только явное разрешение короткого чтения указанной модели: 64 prompt / 16 generation / 1 повтор. Отказ при compute-процессах, загрузке GPU >5% или занятой памяти >1024 МиБ |
| `./nexus-update caddy [VERSION]` | linux_amd64 tarball, SHA-256 из checksums релиза, validate, caddy.prev, restart gateway, HTTPS health; автоматическое восстановление при ошибке |
| `./nexus-update voice` | Снимок uv.lock, upgrade/sync, restart voice, health, TTS WAV → STT. При ошибке старый lock/sync/restart/smoke. Верхние pins torch/torchaudio <=2.5.1 обязательны |
| `./nexus-update rollback canvas\|ik-llama\|caddy\|voice` | Предыдущее состояние последнего успешного обновления данного компонента. Запись отката расходуется только после успеха |

`--dry-run` работает со всеми командами: только план, без сети, файлов, журнала
и вызовов systemd. Другого «обновить всё» нет.

Снимки создаются в собственных новых `~/Agents/Backups/update-<дата>-<компонент>-*`;
прочие резервные копии не затрагиваются. Для canvas сохраняются оба manifest/lock,
независимые копии node_modules и UI dist; откат зависимостей не требует npm-сети.
Ссылки вместо рабочих каталогов запрещены. npm lifecycle scripts отключены;
на проверенных версиях это не мешает build. Бинарник Caddy восстанавливается
атомарной заменой inode, что допускает ещё работающий старый процесс.
Журнал и указатели последних снимков — `~/.local/state/ohn/update*`;
модифицирующие команды сериализованы flock. Ошибки обновления возвращают код 1,
даже если автоматический откат прошёл успешно.

Флаги CUDA/GGML/LLAMA и компиляторов берутся из текущего CMakeCache.txt;
дополнительно включён `CMAKE_BUILD_RPATH_USE_ORIGIN=ON`: текущая сборка содержит
абсолютные RUNPATH, которые сломались бы после переименования каталога.
Параллелизм ограничен четырьмя jobs. Перед сборкой требуется минимум 4 ГиБ либо
двойной размер текущего build плюс 1 ГиБ — что больше. Занятость проверяется
перед работой, --version и swap. Старый `build.old-1006` не трогается.
Для бинарников используется `NCCL_SOCKET_IFNAME=lo`, как в launcher.

Валидация Caddy получает те же каталоги и LAN IP (включая опубликованный
launcher файл `$XDG_RUNTIME_DIR/ohn-lan-ip`), но **ключ-заглушку**:
секретный session.env не читается. После restart unit использует своё настоящее
окружение. API smoke идёт через HTTPS gateway, который сам добавляет авторизацию.
В памяти читается `/api/settings`, проверяется локальный LLM URL, создаётся беседа
без initial_message и с autotitle=false, проверяется сохранённый hook_config,
беседа удаляется в finally. Ответы settings/HTTP и ключи не журналируются.
Ни `/run`, ни сообщения в `/events`, ни запросы LLM не используются.

Проверено 25.10.2026:

- `./nexus-update check` → **0**, [check.log](check.log): canvas 1.30.1 → 1.33.0;
  agent-server **1.57.0 → 1.58.1**; automation **1.23.2 → 1.25.1**;
  ik_llama cea2d61 → 804ee29c, отставание **41 commit**; Caddy **v2.11.7**, обновления нет.
  Voice предлагает обновления fastapi, hydra-core, omegaconf, pycparser,
  sentencepiece и starlette; torch остаётся 2.5.1+cpu.
- `./nexus-update check --offline` → **0**, [check-offline.log](check-offline.log).
- Для каждой команды, с явной версией и без неё, включая четыре rollback и bench:
  `./nexus-update … --dry-run` → **14/14 код 0**, журнал не изменился;
  точные argv в [dry-run-results.json](dry-run-results.json).
- `bash -n nexus-update` → **0**. Shellcheck отсутствует; не устанавливался.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_update` → **0**, **17 тестов**:
  ошибки install/build/health, checksum Caddy, восстановление lock Voice,
  gates GPU/портов, swap/rollback ik_llama, отсутствие сообщений LLM,
  запрет ссылок из песочницы в живое дерево. Внешние команды здесь подменены.
- В **независимой копии** `/tmp/nexus-update-test.038q2b41`:
  `./nexus-update canvas 1.33.0 --sandbox /tmp/nexus-update-test.038q2b41` → **0**;
  `./nexus-update rollback canvas --sandbox /tmp/nexus-update-test.038q2b41` → **0**.
  Логи: [обновление](canvas-update.log), [откат](canvas-rollback.log).
  Этот режим допускается только для canvas/rollback canvas под `/tmp/nexus-update-test.*`;
  службы, health и API smoke явно пропускаются.
- `PYTHONDONTWRITEBYTECODE=1 python3 test_canvas_failure.py /tmp/nexus-update-test.038q2b41` → **0**:
  тест намеренно добавил отсутствующий deep import **только в overlay копии**.
  Реальный build получил код 1; updater восстановил 1.30.1 и пересобрал её.
  Хэши четырёх manifest/lock совпали, исходник восстановлен.
  [Лог ожидаемого отказа и восстановления](canvas-failure-rollback.log).
- **ui с 1.33.0 собирается; сломанных настоящих overlay imports нет.**
  Есть предупреждение Vite о размере bundle, ошибок build нет.
  `python3 ../i18n-ru/check.py` → **0**, 475 ключей проверены.
  Дополнительное сравнение English canvas с overlay выявило **16 отсутствующих
  русских ключей**; имена перечислены в canvas-update.log. Старый check.py
  проверяет свой фиксированный набор, поэтому сам эти новые пробелы не обнаруживает.
- [live-integrity.json](live-integrity.json): **25/25** отпечатков живых
  manifest/lock/dist/Caddy и списка размеров/mtime `.venv` не изменились.

Не проверены: настоящие обновления/перезапуски служб, live health/API guard на
новом agent-server 1.58.1, реальный TTS/STT после uv upgrade, загрузка/validate
новой Caddy, CUDA-сборка и benchmark. Эти операции оставлены руководителю.
Runtime UI с 1.33.0 не проверялся: доказана сборка, не весь пользовательский путь.
Модели/GGUF, старые установки и guard.py не менялись; секретные файлы не читались;
sudo, commit и push не использовались.
