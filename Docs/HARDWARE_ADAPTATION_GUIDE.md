# Руководство по адаптации OpenHands Nexus под различное оборудование (Hardware Adaptation Guide)

> **Концепция портативности:**  
> Референсная конфигурация OpenHands Nexus настроена на рабочую станцию с **48 GB RAM** и **Dual GPU (RTX 5060 Ti 16 GB + RTX 2080 Ti 22 GB)**.  
> Однако архитектура станции полностью модульная. Вы можете легко запустить OpenHands Nexus на **одном GPU**, на **другой связке видеокарт**, с **другим объёмом оперативной памяти** и с **любыми вашими моделями**.

---

## 1. Конфигурация с одной видеокартой (Single GPU Setup)

Если в вашей системе установлена одна дискретная видеокарта NVIDIA (например, RTX 3060 12GB, RTX 4070 16GB, RTX 3090/4090 24GB):

### Шаг 1: Изменение параметров в `llama-swap/config.yaml`
Откройте [`llama-swap/config.yaml`](../llama-swap/config.yaml) и для каждой используемой модели:
1. Замените `-dev CUDA0,CUDA1` на `-dev CUDA0`.
2. Удалите параметр `-ts ...` (тензорный сплит не нужен для одного GPU).
3. Удалите `-sm layer` (если указан).

*Пример для одной видеокарты:*
```yaml
  my-model:
    cmd: >-
      K:\Project\ik_llama\bin\llama-server.exe
      -m K:\Project\Models\MyModel.gguf
      -c 32768
      -ngl 999
      -dev CUDA0
      -ctk q8_0
      -ctv q8_0
      -fa on
      --host 127.0.0.1
      --port ${PORT}
```

### Шаг 2: Выбор модели под объём вашей видеопамяти (VRAM Matrix)

| Объём VRAM | Рекомендуемые модели GGUF | Квантование | Размер контекста (`-c`) | Ожидаемая скорость |
| :--- | :--- | :---: | :---: | :---: |
| **8 – 12 GB** | Qwen 2.5 Coder 7B, DeepSeek-R1-Distill-Qwen-7B | Q8_0 / Q4_K_M | 32,768 (32K) | 50 – 70 tok/s |
| **16 GB** | Qwen 2.5 Coder 14B, DeepSeek-R1-Distill-14B | Q8_0 / Q5_K_M | 32,768 – 65,536 (32K-64K) | 40 – 55 tok/s |
| **16 GB** | Qwen 3.8 27B Opus v2 (частичный оффлоад) | Q4_K_M | 32,768 (32K) с `-ngl 40` | 20 – 30 tok/s |
| **24 GB (RTX 3090/4090)** | **Ornith 1.5 Coder 35B ICE** (целиком в VRAM!) | Q4_K_M / Q5_K_M | 65,536 – 131,072 (64K-128K) | **70 – 85 tok/s** |
| **24 GB (RTX 3090/4090)** | Qwen 2.5 Coder 32B | Q4_K_M | 65,536 (64K) | 35 – 45 tok/s |

> [!TIP]
> На видеокартах с 24 GB VRAM модель **Ornith 1.5 Coder 35B ICE** помещается в видеопамять целиком (`-ngl 999`) и выдаёт феноменальную скорость генерации качественного кода (до 80+ токенов в секунду).

---

## 2. Конфигурация с двумя видеокартами (Dual GPU Setup)

Если у вас связка из двух GPU, отличная от нашей (16 GB + 22 GB):

### Расчет формулы `-ts X,Y` (Tensor Split)
Параметр `-ts <CUDA0_weight>,<CUDA1_weight>` задаёт весовые доли распределения слоёв модели между видеокартами:

$$\text{Доля GPU 0} = \frac{X}{X + Y}, \quad \text{Доля GPU 1} = \frac{Y}{X + Y}$$

**Примеры расчета под типовые связки:**
* **Две одинаковые карты (например, 2x RTX 3060 12GB или 2x RTX 4070 16GB):**
  ```yaml
  -dev CUDA0,CUDA1 -ts 16,16
  # или просто -ts 1,1
  ```
* **Карта 12 GB + Карта 16 GB:**
  ```yaml
  -dev CUDA0,CUDA1 -ts 12,16
  ```
* **Карта 8 GB + Карта 16 GB:**
  ```yaml
  -dev CUDA0,CUDA1 -ts 8,16
  ```
* **Наша референсная связка (16 GB + 22 GB):**
  ```yaml
  -dev CUDA0,CUDA1 -ts 13,26 -sm layer
  # Пропорция 13:26 идеально балансирует свободный запас VRAM (~2.0 GB на обеих картах)
  ```

---

## 3. Адаптация под объём оперативной памяти (RAM)

Оперативная память критически важна, если вы используете гибридный оффлоад (часть слоев на GPU, часть на CPU):

* **16 GB RAM:**
  - Рекомендуется запускать модели, которые **целиком помещаются в VRAM** (до 14B параметров).
  - Установите размер контекста `-c 32768` (32K), чтобы избежать дефицита системной памяти.
* **32 GB RAM:**
  - Позволяет комфортно запускать модели до **35B параметров** с полным контекстом до 64K–128K.
  - Допускается частичный оффлоад 5–10 слоев на процессор.
* **48 GB – 64 GB RAM:**
  - Позволяет запускать сверхтяжелые модели уровня **Qwen 3.5 122B A10B** (размер GGUF ~41.5 GB).
  - При наличии 38 GB VRAM верхние 15 слоев работают через хостовую RAM с ускорением через **GPU Hot-Expert Cache** ([подробнее в отчете](QWEN122_EXPERT_CACHE_BENCHMARK.md)).

---

## 4. Как добавить собственную модель в систему

Процесс добавления любой новой модели состоит из трёх простых шагов:

### Шаг 1: Скачайте файл модели GGUF
Создайте подкаталог в `Models/` и поместите туда файл весов:
```powershell
# Например:
K:\Project\Models\MyModel\qwen2.5-coder-14b-instruct-q8_0.gguf
```

### Шаг 2: Зарегистрируйте модель в `llama-swap/config.yaml`
Добавьте секцию конфигурации:
```yaml
models:
  my-model:
    aliases:
    - openai/my-model
    proxy: http://127.0.0.1:${PORT}
    cmdStop: powershell -NoProfile -Command "Stop-Process -Id ${PID} -Force; Start-Sleep -Seconds 3"
    unloadTimeout: 15
    cmd: >-
      K:\Project\ik_llama\bin\llama-server.exe
      -m K:\Project\Models\MyModel\qwen2.5-coder-14b-instruct-q8_0.gguf
      -c 32768
      -ngl 999
      -dev CUDA0
      -fa on
      --jinja
      --host 127.0.0.1
      --port ${PORT}
```
Благодаря флагу `-watch-config`, `llama-swap` подхватит новую модель автоматически без перезапуска всей станции!

### Шаг 3: Добавьте рабочий профиль в UI
В каталоге [`Config/working-profile-templates/`](../Config/working-profile-templates/) создайте файл `my-profile.json`:
```json
{
  "id": "my-profile",
  "name": "My Custom Model",
  "category": "solo",
  "model_alias": "openai/my-model",
  "description": "Моя персональная модель для локального кодинга",
  "icon": "⚡",
  "default_mode": "direct",
  "modes": {
    "direct": {
      "name": "Direct",
      "reasoning_budget": 0,
      "max_output_tokens": 8192
    }
  }
}
```
После этого модель мгновенно появится в селекторе профилей Agent Canvas и в мобильном PWA!
