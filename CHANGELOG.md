# Changelog

Все заметные изменения в проекте **OpenHands Nexus** документируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/), проект придерживается [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-09

### Добавлено
- **Working Profiles:** система из 17 профилей (Qwen 3.8 27B, Ornith 1.5 35B, Qwen3-Next 80B, тандемы и Team-Full) с серверной синхронизацией.
- **Remote Control UI:** компактная плашка выбора профилей с автосхлопыванием при фокусе на поле ввода и защитой от виртуальной клавиатуры.
- **Thinking / Reasoning Control:** динамическое переключение уровней рассуждений (Direct, Low, Medium, High, Deep).
- **Local Voice Bridge:** локальное распознавание русской речи GigaAM v3 (STT ~300мс) и двухдвижковая озвучка (Dual-Engine TTS: Supertonic 3 + Samsung/Android TTS).
- **HTTPS LAN Gateway (PWA):** двухуровневая X.509 архитектура сертификатов, PWA манифест, Service Worker, адаптивный мобильный интерфейс для планшетов и смартфонов.
- **Физическая валидация на Samsung Galaxy Tab S9 Ultra:** полное сквозное тестирование сценариев управления через Wi-Fi LAN.
- **Портативность и восстановление:** скрипты setup.ps1, ackup-station.ps1, estore-station.ps1, ecover.ps1 с 34 системными тестами.
- **DevOps и стандарты:** добавлены .editorconfig, .gitattributes, .gitleaks.toml, pyproject.toml, LICENSE (MIT), единый CLI-диспетчер openhands.cmd.

### Исправлено
- Устранена коллизия высоты панели профиля с виртуальной клавиатурой на мобильных экранах.
- Оптимизирована выгрузка моделей в VRAM (LRU swapping через llama-swap).
- Обеспечено гарантированное закрытие аудиотреков микрофона при завершении записи.
