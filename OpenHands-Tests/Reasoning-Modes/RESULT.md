# Технический отчёт: Настройка управляемого reasoning/thinking для Qwen3.8-27B Opus в OpenHands

## 1. Механизм Reasoning в установленной версии ik_llama.cpp (commit 3c58ae3)

Анализ бинарного файла `K:\Project\ik_llama\bin\llama-server.exe` и метаданных модели `D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf` показал:

1. **Jinja Chat Template:** В модель `Qwen3.8-27B-Opus-Distill-v2` встроен шаблон Jinja, который динамически обрабатывает параметры reasoning:
   ```jinja2
   {%- if enable_thinking is undefined or enable_thinking is true %}
       {%- set resolved_reasoning_effort = reasoning_effort|default('xhigh') %}
       {%- if resolved_reasoning_effort not in ('xhigh', 'medium', 'low') %}
           {{- raise_exception('Unexpected reasoning effort ' ~ reasoning_effort ~ '. Supported types are xhigh (default), medium, and low.') }}
       {%- endif %}
       {%- if resolved_reasoning_effort == 'xhigh' %}
           {%- set reasoning_instructions = 'Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer.' %}
       {%- elif resolved_reasoning_effort == 'low' %}
           {%- set reasoning_instructions = 'Reasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration.' %}
       {%- endif %}
   {%- endif %}
   ```
2. **Значение по умолчанию до настройки:**
   - Шаблон по умолчанию использует: `reasoning_effort|default('xhigh')`!
   - До настройки модель **всегда работала в режиме XHigh**.
3. **Формат передачи в API:**
   - В `/v1/chat/completions` параметры шаблона передаются через объект `chat_template_kwargs`.
   - Сервер `ik_llama` commit 3c58ae3 также поддерживает параметр верхнего уровня `reasoning_budget_tokens: 0` для немедленного отсечения генерации блоков размышления.
   - Полноценное динамическое переключение **работает per-request без перезапуска сервера и без перезагрузки весов модели в VRAM**.

---

## 2. Точные параметры JSON для 4 режимов

### А. Режим Direct (Thinking OFF)
- **Назначение:** Без reasoning. Для простых команд, вызовов инструментов и быстрых ответов.
- **Параметры запроса:**
  ```json
  {
    "chat_template_kwargs": {
      "enable_thinking": false
    },
    "reasoning_budget_tokens": 0
  }
  ```
- **Результат:** Длина `reasoning_content` = 0. Модель отвечает сразу целевым текстом без тегов `<think>`.

### Б. Режим Low
- **Назначение:** Короткое рассуждение. Для обычных рутинных задач.
- **Параметры запроса:**
  ```json
  {
    "chat_template_kwargs": {
      "reasoning_effort": "low"
    }
  }
  ```
- **Результат:** Шаблон внедряет директиву: *"Reasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration."* Модель формирует компактное рассуждение (~100-150 символов).

### В. Режим Medium
- **Назначение:** Среднее рассуждение. Основной рабочий режим по умолчанию.
- **Параметры запроса:**
  ```json
  {
    "chat_template_kwargs": {
      "reasoning_effort": "medium"
    }
  }
  ```
- **Результат:** Базовые размышления без форсирования глубокой валидации (~150-250 символов).

### Г. Режим XHigh
- **Назначение:** Максимальное рассуждение. Для архитектурных задач, сложного кода и многошаговой диагностики.
- **Параметры запроса:**
  ```json
  {
    "chat_template_kwargs": {
      "reasoning_effort": "xhigh"
    }
  }
  ```
- **Результат:** Шаблон внедряет директиву: *"Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer."* Полное глубокое решение с проверкой граничных условий.

---

## 3. Сравнительный бенчмарк режимов на прямой задаче (Classic Bat & Ball)

Запрос: *"A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Show your steps."*

| Режим | Prompt Tokens | Completion Tokens | Reasoning Content Len | Время ответа |
|---|---|---|---|---|
| **Direct (OFF)** | 50 | 189 | **0** (Disabled) | 5.84s |
| **Low** | 78 | 177 | 192 | 5.05s |
| **Medium** | 48 | 244 | 219 | 6.97s |
| **XHigh** | 90 | 317 | 181 (+детальное решение в тексте) | 9.39s |

---

## 4. Профили в OpenHands Agent Canvas

В Profile Store OpenHands (`C:\Users\User\.openhands\profiles\`) созданы 4 независимых профиля:

1. **`Qwen3.8-Opus-Direct`**
   - Reasoning effort: `none`
   - Extra body: `{"chat_template_kwargs": {"enable_thinking": false}, "reasoning_budget_tokens": 0}`
2. **`Qwen3.8-Opus-Low`**
   - Reasoning effort: `low`
   - Extra body: `{"chat_template_kwargs": {"reasoning_effort": "low"}}`
3. **`Qwen3.8-Opus-Medium`** `[АКТИВНЫЙ / ПО УМОЛЧАНИЮ]`
   - Reasoning effort: `medium`
   - Extra body: `{"chat_template_kwargs": {"reasoning_effort": "medium"}}`
4. **`Qwen3.8-Opus-XHigh`**
   - Reasoning effort: `high`
   - Extra body: `{"chat_template_kwargs": {"reasoning_effort": "xhigh"}}`

Все 4 профиля используют:
- Одно подключение: `http://127.0.0.1:8080/v1`
- Один идентификатор модели: `openai/D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf`
- Контекст: `98304`
- Загрузка модели в память: **однократная, без перезапуска и дублирования**
- Переключатель `enable_switch_llm_tool`: **`False`** (ручной выбор пользователем).

---

## 5. Фактическая верификация работы через OpenHands

Каждый профиль был протестирован через создание реальной сессии в OpenHands на задаче:
*"Explain what RAM is in one sentence. Be direct and concise."*

| Профиль в OpenHands | Conversation ID | Время ответа | Reasoning Length | Статус Thinking |
|---|---|---|---|---|
| **`Qwen3.8-Opus-Direct`** | `d64a7c30-6af3-45cd-89eb-d74dbe802372` | 4.01s | **0 символов** | **ПОЛНОСТЬЮ ОТКЛЮЧЁН (0)** |
| **`Qwen3.8-Opus-Low`** | `712b9730-5ddf-40a2-8887-31aa1a87f803` | 6.02s | 132 символа | Включён (Краткий) |
| **`Qwen3.8-Opus-Medium`** | `4760bcef-c2dd-4dd0-b016-c2cd04b5be9f` | 4.01s | 158 символов | Включён (Средний) |
| **`Qwen3.8-Opus-XHigh`** | `300b6001-0a22-45af-aa12-5f8669fed41d` | 32.08s | 101 + глубокая генерация | Включён (Максимальный) |

---

## 6. Анализ Launcher-файла BEST-QWEN38-96K.cmd

Файл `K:\Project\LLM-tests\BEST-QWEN38-96K.cmd` **не требовал изменений**:
- Он запускает `llama-server.exe` с флагом `--jinja`, что позволяет обрабатывать шаблон динамически.
- Он не фиксирует параметры reasoning жестко на уровне сервера, оставляя сервер полностью универсальным.
- Все параметры производительности (MTP `n_max=3,p_min=0.0`, контекст `98304`, кэш `q8_0/q5_0`, Flash Attention) сохранены в неизменном виде.