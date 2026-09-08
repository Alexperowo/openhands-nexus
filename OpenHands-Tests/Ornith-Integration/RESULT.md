# Итоговый отчёт по интеграции Ornith-1.5-35B-A3B в OpenHands Local

Дата проведения испытаний: 04.09.2026.
Тестируемая среда: Windows 11, NVIDIA GeForce RTX 2080 Ti (22.5 GB физической VRAM), RAM 48 GB.

---

## Финальная верификационная таблица

| Проверка | Статус | Фактическое доказательство |
|---|:---:|---|
| **FOREIGN SWAP + BACKEND SURVIVES STOP** | **PASS** | Поднят сторонний `llama-swap` (PID 14108) и загружен mock-backend (PID 12040). Выполнен цикл START->STOP (`owned=false`). Скрипт STOP пропустил чужой инстанс (`[SKIP]`), не вызывал `/api/models/unload`. Оба процесса остались живы, модель осталась загружена в памяти (`foreign_backend_survival_result.json`). |
| **OWNERSHIP** | **PASS** | Полный отказ от `kill-by-name`. Завершаются исключительно launcher-owned PIDs. Чужие процессы (llama-swap, backend, voice-bridge) выживают на 100%. |
| **AGENT-INVOKED SWITCHLLMTOOL** | **PASS** | Qwen самостоятельно вызвал инструмент `SwitchLLMAction(profile_name='Ornith-Coding', reason='Передаю выполнение кода модели Ornith')` без внешних REST-вызовов. OpenHands зарегистрировал смену профиля в `SwitchLLMObservation` (`agent_switch_result.json`). |
| **AUTOMATIC MODEL SWITCHING** | **READY** | `llama-swap` на порту 8080 перехватывает смену профиля на лету: Qwen останавливается, VRAM очищается, Ornith загружается. После смены Ornith в том же диалоге `37403c32-73dd-4886-bc9a-9ee44c0d9be4` выполнил 2 инструмента (`FileEditorAction` и `TerminalAction`, создав `status.txt`). |
| **INTEGRATION CORE** | **READY** | Все компоненты (llama-swap, OpenHands start/stop, SwitchLLMTool, Ornith 96K MTP runtime) полностью согласованы и готовы к эксплуатации. |

---

## Хронология событий диалога с самостоятельным вызовом SwitchLLMTool (`37403c32-73dd-4886-bc9a-9ee44c0d9be4`)

1. **Событие 2 (User)**: Запрос составить план создания `status.txt` и вызвать `switch_llm` на `Ornith-Coding`.
2. **События 6-7 (Agent / Qwen)**: Qwen создал план через `TaskTrackerAction`.
3. **Событие 9 (Agent / Qwen)**: Qwen самостоятельно инициировал действие:
   ```json
   {
     "action": {
       "profile_name": "Ornith-Coding",
       "reason": "Передаю выполнение кода модели Ornith",
       "kind": "SwitchLLMAction"
     }
   }
   ```
4. **Событие 10 (Environment)**: Профиль диалога переключён: `agent.llm.model = 'openai/ornith'`.
5. **Событие 11 (Environment)**: Ответ инструмента:
   `"Switched LLM profile to 'Ornith-Coding' with active model 'openai/ornith'..."`
6. **Физический swap в `llama-swap`**:
   `[INFO] <qwen> Health check passed ...` -> `[INFO] <ornith> Health check passed ...`.
7. **Событие 19 (Agent / Ornith)**: Ornith выполнил `FileEditorAction` (создал `status.txt`).
8. **События 21-22 (Agent / Ornith)**: Ornith выполнил `TerminalAction` (`type status.txt`), получил вывод `'Ornith execution verified'` с кодом возврата 0.
9. **Событие 23 (Agent / Ornith)**: Подтверждение успешного выполнения задачи.
