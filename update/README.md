# Обновление движков Nexus на Linux

Точка входа — `./nexus-update`, Bash с `set -euo pipefail`; реализация —
`nexus_update.py`, только стандартная библиотека Python 3.11+.
Дерево вычисляется относительно скрипта, backend — `~/backend/ik_llama-fresh`.
Без аргументов выполняется **только check**. Sudo не используется.

| Команда | Действие |
|---|---|
| `./nexus-update [check]` | Установленные/доступные версии: npm, pins из tarball, git ls-remote и отставание, GitHub releases Caddy и llama-swap, uv resolver dry-run для голоса, PyPI для команд экрана (hai-drivers). Проекты/окружения не меняются; допустимы журнал и кэши инструментов |
| `./nexus-update check --offline` | Без сети; доступные версии — unknown |
| `./nexus-update canvas [VERSION]` | Точная одинаковая версия в двух проектах, build overlay, отчёт локали, restart agent → gateway, health и API smoke guard. При ошибке восстановление обоих проектов, build, restart и health |
| `./nexus-update ik-llama [COMMIT]` | По умолчанию origin/main; проверки занятости, диска и чистоты tracked-файлов, новый каталог сборки, --version до/после swap. Сохраняет build.prev; службу модели не запускает |
| `./nexus-update ik-llama [COMMIT] --bench /path/model.gguf` | Только явное разрешение короткого чтения указанной модели: 64 prompt / 16 generation / 1 повтор. Отказ при compute-процессах, загрузке GPU >5% или занятой памяти >1024 МиБ |
| `./nexus-update caddy [VERSION]` | linux_amd64 tarball, SHA-256 из checksums релиза, validate, caddy.prev, restart gateway, HTTPS health; автоматическое восстановление при ошибке |
| `./nexus-update llama-swap [VERSION]` | linux_amd64 tarball, SHA-256 из checksums релиза, `--version`, llama-swap.prev. ohn-models перезапускается и проверяется `/health`, только если уже работал: модели ради обновления не запускаются |
| `./nexus-update voice` | Снимок uv.lock, upgrade/sync, restart voice, health, TTS WAV → STT. При ошибке старый lock/sync/restart/smoke. Верхние pins torch/torchaudio <=2.5.1 обязательны |
| `./nexus-update rollback canvas\|ik-llama\|caddy\|llama-swap\|voice` | Предыдущее состояние последнего успешного обновления данного компонента. Запись отката расходуется только после успеха |

`--dry-run` работает со всеми командами: только план, без сети, файлов, журнала
и вызовов systemd. Другого «обновить всё» нет.

Снимки создаются в собственных новых `~/Agents/Backups/update-<дата>-<компонент>-*`;
прочие резервные копии не затрагиваются. На компонент хранится одна копия — последняя
удачного обновления; её удаляют следующее удачное обновление и откат, копию неудачного — автоматический откат. Для canvas сохраняются оба manifest/lock,
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

## Проверки

```sh
python3 test_update.py      # внешние команды подменены: ошибки install/build/health,
                            # checksum Caddy, откат lock голоса, занятость GPU и портов,
                            # swap и откат ik_llama, ни одного сообщения модели
./nexus-update check --offline
./nexus-update canvas --dry-run   # и любая другая команда: только план
```

Настоящий сбой сборки и восстановление canvas проверяются в отдельной копии дерева
под `/tmp/nexus-update-test.*` (службы, health и API smoke там пропускаются):

```sh
./nexus-update canvas 1.33.0 --sandbox /tmp/nexus-update-test.XXXX
./nexus-update rollback canvas --sandbox /tmp/nexus-update-test.XXXX
python3 test_canvas_failure.py /tmp/nexus-update-test.XXXX   # битый import в overlay → откат
```

После обновления canvas выводится список ключей английской локали, которых нет
в `ui/src/locales/ru.json`: это отчёт, обновление он не останавливает.
