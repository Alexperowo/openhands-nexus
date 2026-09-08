# Исследование архитектуры: Ornith-1.5, SwitchLLMTool и llama-swap

## 1. Chat Template и управление рассуждением (Reasoning) в Ornith-1.5

Прямой анализ Jinja-шаблона, извлечённого из метаданных GGUF `K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf`, показал следующую структуру генерации системного промпта и тегов мышления:

```jinja
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}
```

### Выводы по шаблону:
1. **Нативная поддержка `enable_thinking`**:
   - При `enable_thinking: false` шаблон сразу же закрывает блок `<think>\n\n</think>\n\n`, тем самым принуждая модель выдавать прямой ответ без шагов рассуждения.
   - При `enable_thinking: true` (или по умолчанию) шаблон открывает `<think>\n` и ждёт поток CoT-рассуждений.
2. **Формат Tool Calling**:
   - Модель имеет встроенную разметку `<tools>` и тегов вызова функций `<tool_call>\n<function=name>...`.
3. **Поведение OpenAI API**:
   - При вызове через `chat_template_kwargs: {"enable_thinking": false}` поле `reasoning_content` в ответе API пустое (0 токенов рассуждения), а `content` содержит прямой ответ. Наличие закрытого тега `<think></think>` в префиксе шаблона не является ошибкой и обрабатывается бэкендом прозрачно.

---

## 2. Анализ SwitchLLMTool в Agent Canvas / Agent Server

Исследование локального исходного кода `C:\Users\User\AppData\Local\uv\cache\...\openhands\sdk\tool\builtins\switch_llm.py` установило:

1. **Хранилище профилей**:
   - Инструмент динамически обращается к `LLMProfileStore().list_summaries()`, считывая все сохранённые `.json` файлы из каталога `C:\Users\User\.openhands\profiles\`.
2. **Механизм переключения**:
   - Класс `SwitchLLMExecutor` вызывает `conversation.switch_profile(action.profile_name)`.
   - Текущий шаг агента завершается текущей моделью. Переключение вступает в силу на **следующем** шаге LLM (`Future agent steps will use this profile`).
3. **Сохранение состояния (State Retention)**:
   - Вся история сообщений, контекст диалога, переменные и память хранятся в объекте `LocalConversation`. При переключении профиля объект диалога не пересоздаётся, теряется 0 сообщений.
4. **Безопасность и обработка ошибок**:
   - Если профиль не найден или содержит невалидные настройки, метод ловит `FileNotFoundError` / `ValueError` / `Exception` и возвращает `SwitchLLMObservation(is_error=True)`. Агент видит ошибку и продолжает работу без падения сервера.
5. **Включение инструмента**:
   - В `C:\Users\User\.openhands\settings.json` параметр `agent_settings.enable_switch_llm_tool` отвечает за передачу инструмента агенту.

---

## 3. Исследование Model Swap и выбор llama-swap

Для исключения конфликтов VRAM (так как Qwen 21.8 GB и Ornith 20.7 GB физически не помещаются на одной карте 22 GB) исследовано решение `mostlygeek/llama-swap`:

1. **Платформенная совместимость**:
   - Доступен официальный портативный бинарник Windows AMD64 (`v252`, SHA256 верифицирован).
   - Полная совместимость с `ik_llama\bin\llama-server.exe`.
2. **Управление процессами и Ownership**:
   - В `config.yaml` бэкенд запускается напрямую через `cmd: llama-server.exe ... --port ${PORT}` без промежуточных батников (`.cmd`).
   - `llama-swap` отслеживает точный PID запущенного бэкенда, не использует опасный mass-kill по имени процесса или номеру порта.
   - При смене модели бэкенд корректно завершается, освобождая 100% VRAM перед стартом новой модели.
3. **OpenAI-совместимый роутинг**:
   - Слушает один порт (например, 8080 или 18090).
   - Автоматически инспектирует поле `model` в JSON-запросе и маршрутизирует его к нужной модели.
   - Поддерживает `aliases` (псевдонимы) для обратной совместимости со старыми путями.
