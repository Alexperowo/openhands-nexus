# Конфигурация профилей моделей в OpenHands Local

Каталог профилей: `C:\Users\User\.openhands\profiles\`

## 1. Унифицированные Model ID
Для прозрачной интеграции с `llama-swap`:
- Все профили **Qwen3.8** используют ID: `"model": "openai/qwen"`
- Все профили **Ornith-1.5** используют ID: `"model": "openai/ornith"`

Все профили обращаются к единому входному шлюзу:
`"base_url": "http://127.0.0.1:8080/v1"`

---

## 2. Спецификация профилей Ornith-1.5

### Профиль 1: `Ornith-Direct`
- **Файл**: `Ornith-Direct.json`
- **Назначение**: Быстрые команды, терминал, чтение/запись файлов, простые вызовы функций без траты токенов на рассуждения.
- **Параметры сэмплинга**:
  - `temperature`: `0.6`
  - `top_p`: `0.95`
  - `max_input_tokens`: `98304`
  - `max_output_tokens`: `4096`
  - `reasoning_effort`: `"none"`
  - `native_tool_calling`: `true`
  - `litellm_extra_body`:
    ```json
    {
      "chat_template_kwargs": {
        "enable_thinking": false
      },
      "reasoning_budget_tokens": 0
    }
    ```
- **Результаты проверки API**:
  - `reasoning_content`: пустой (0 токенов).
  - Время генерации: 1.5–9 с.

### Профиль 2: `Ornith-Coding`
- **Файл**: `Ornith-Coding.json`
- **Назначение**: Написание кода, сложный рефакторинг, диагностика ошибок выполнения, многошаговая логика инструментов.
- **Параметры сэмплинга**:
  - `temperature`: `0.6`
  - `top_p`: `0.95`
  - `max_input_tokens`: `98304`
  - `max_output_tokens`: `4096`
  - `reasoning_effort`: `"medium"`
  - `native_tool_calling`: `true`
  - `litellm_extra_body`:
    ```json
    {
      "chat_template_kwargs": {
        "enable_thinking": true
      }
    }
    ```
- **Результаты проверки API**:
  - `reasoning_content`: заполнен полным блоком размышлений (~1 000 токенов CoT).
  - Модель генерирует строгий, типизированный Python/Bash код.

---

## 3. Проверка Zero-Swap (Direct <-> Coding)
В ходе тестов подтверждено:
- Переключение между `Ornith-Direct` и `Ornith-Coding` обрабатывается **внутри одного и того же процесса `llama-server.exe`** (PID 12680 сохранился без изменений).
- Физической перезагрузки модели не происходит, время отклика составляет 1–4 секунды.

---

## 4. Сохранение существующих профилей Qwen
Существующие профили Qwen сохранены и обновлены с сохранением резервной копии в `K:\Project\OpenHands-Tests\Ornith-Integration\profiles_backup\`:
- `Qwen3.8-Opus-Direct.json`
- `Qwen3.8-Opus-Low.json`
- `Qwen3.8-Opus-Medium.json` (основной рабочий профиль по умолчанию)
- `Qwen3.8-Opus-XHigh.json`
- `Qwen38_Opus_96K.json`
- `default.json`
