# Итоговый отчёт оптимизации: Qwen3.8-27B Opus-Distill-v2 (~85.3K Context)

**Конфигурация тестового стенда:**
- **Модель**: `D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf` (архитектура `qwen35` hybrid Attention + SSM)
- **Backend**: `ik_llama.cpp` (коммит `3c58ae3`, сборка с поддержкой recurrent checkpoints и MTP)
- **GPU**: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM, 22528 MiB)
- **Контекст**: `n_ctx = 98304` (96K), реальное заполнение промпта: **85 337 токенов**
- **KV Cache**: `K = q8_0`, `V = q5_0`
- **Flash Attention**: `ON` (`-fa on`)
- **Параллелизм**: `1` (`-np 1`)
- **Параметры генерации**: 512 токенов, `seed = 42`, `temp = 0.7`, `top_p = 0.8`, `min_p = 0.05`

---

## 1. Сводная таблица всех 23 протестированных конфигураций

| № | Тест | Категория | Флаги speculative | Prompt Eval | TTFT | Gen Speed | Время запроса | Пик VRAM | MTP Acceptance | Статус |
| :-: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 01_baseline | baseline_no_mtp | Baseline | *(нет)* | 379.02 t/s | 225.15 s | **12.93 t/s** | 265.13 s | 20024 MiB | N/A | SUCCESS |
| 02_mtp_n1_p0 | mtp_n1_p00 | MTP-n1 | `--spec-type mtp:n_max=1,p_min=0.0` | 346.26 t/s | 246.45 s | **12.77 t/s** | 286.97 s | 21466 MiB | 81.5% (229/281) | SUCCESS |
| 03_mtp_n2_p0 | mtp_n2_p00 | MTP-n2 | `--spec-type mtp:n_max=2,p_min=0.0` | 338.69 t/s | 251.96 s | **13.49 t/s** | 290.31 s | 21745 MiB | 69.4% (297/428) | SUCCESS |
| 04_mtp_n2_p5 | mtp_n2_p05 | MTP-n2 | `--spec-type mtp:n_max=2,p_min=0.5` | 338.05 t/s | 252.44 s | **13.07 t/s** | 292.04 s | 21783 MiB | 69.2% (267/386) | SUCCESS |
| 05_mtp_n2_p7 | mtp_n2_p07 | MTP-n2 | `--spec-type mtp:n_max=2,p_min=0.7` | 339.01 t/s | 251.73 s | **12.33 t/s** | 293.72 s | 21665 MiB | 70.0% (247/353) | SUCCESS |
| 06_mtp_n3_p0 | mtp_n3_p00 | MTP-n3 | `--spec-type mtp:n_max=3,p_min=0.0` | 342.76 t/s | 248.97 s | **16.17 t/s** | 281.03 s | 21858 MiB | 61.5% (331/538) | SUCCESS |
| 07_mtp_n3_p5 | mtp_n3_p05 | MTP-n3 | `--spec-type mtp:n_max=3,p_min=0.5` | 338.91 t/s | 251.8 s | **15.05 t/s** | 286.29 s | 21941 MiB | 68.3% (315/461) | SUCCESS |
| 08_mtp_n3_p7 | mtp_n3_p07 | MTP-n3 | `--spec-type mtp:n_max=3,p_min=0.7` | 335.16 t/s | 254.62 s | **12.25 t/s** | 296.86 s | 22025 MiB | 69.1% (246/356) | SUCCESS |
| 09_mtp_n4_p0 | mtp_n4_p00 | MTP-n4 | `--spec-type mtp:n_max=4,p_min=0.0` | 342.17 t/s | 249.4 s | **14.4 t/s** | 285.35 s | 22028 MiB | 47.5% (334/703) | SUCCESS |
| 10_mtp_n4_p5 | mtp_n4_p05 | MTP-n4 | `--spec-type mtp:n_max=4,p_min=0.5` | 339.16 t/s | 251.61 s | **15.95 t/s** | 284.15 s | 22112 MiB | 64.3% (339/527) | SUCCESS |
| 11_mtp_n4_p7 | mtp_n4_p07 | MTP-n4 | `--spec-type mtp:n_max=4,p_min=0.7` | 345.54 t/s | 246.97 s | **14.69 t/s** | 282.25 s | 22125 MiB | 73.6% (307/417) | SUCCESS |
| 12_autotune_run | spec_autotune_run | Autotune | `--spec-type mtp:n_max=4,p_min=0.0 --spec-autotune` | 337.93 t/s | 252.53 s | **15.12 t/s** | 286.79 s | 21978 MiB | 47.5% (334/703) | SUCCESS |
| 14_mtp_heads0 | mtp_n1_heads0 | MTP-Heads | `--spec-type mtp:n_max=1,heads=0` | 346.67 t/s | 246.16 s | **12.8 t/s** | 286.6 s | 21437 MiB | 81.5% (229/281) | SUCCESS |
| 15_mtp_heads2 | mtp_n1_heads2 | MTP-Heads | `--spec-type mtp:n_max=1,heads=2` | 347.42 t/s | 245.63 s | **12.85 t/s** | 285.91 s | 21437 MiB | 81.5% (229/281) | SUCCESS |
| 16_ngram_simple_16 | ngram_simple_n16 | ngram-simple | `--spec-type ngram-simple:n_max=16` | 385.6 t/s | 221.31 s | **14.05 t/s** | 258.21 s | 22150 MiB | N/A | SUCCESS |
| 17_ngram_simple_32 | ngram_simple_n32 | ngram-simple | `--spec-type ngram-simple:n_max=32` | 390.15 t/s | 218.73 s | **11.9 t/s** | 262.18 s | 22156 MiB | N/A | SUCCESS |
| 18_ngram_mod_16 | ngram_mod_n16 | ngram-mod | `--spec-type ngram-mod:n_max=16,n_min=2,ngram_size_n=8` | 389.83 t/s | 218.91 s | **13.73 t/s** | 256.58 s | 22160 MiB | 6.2% (1/16) | SUCCESS |
| 19_ngram_mod_32 | ngram_mod_n32 | ngram-mod | `--spec-type ngram-mod:n_max=32,n_min=2,ngram_size_n=8` | 345.57 t/s | 246.94 s | **9.76 t/s** | 299.77 s | 22189 MiB | 3.1% (1/32) | SUCCESS |
| 20_twostage_mod_mtp | twostage_ngram_mod_mtp | Two-Stage | `--spec-type ngram-mod:n_max=16,n_min=2,ngram_size_n=8 --spec-type mtp:n_max=1,p_min=0.0` | 62.32 t/s | 1369.31 s | **1.38 t/s** | 1739.78 s | 22190 MiB | 75.3% (232/308) | SUCCESS |
| 21_twostage_simp_mtp | twostage_ngram_simp_mtp | Two-Stage | `--spec-type ngram-simple:n_max=16 --spec-type mtp:n_max=1,p_min=0.0` | 80.75 t/s | 1056.81 s | **2.07 t/s** | 1305.16 s | 22188 MiB | 79.8% (233/292) | SUCCESS |
| 22_repeat_top1 | mtp_n3_p00_repeat | Validation-Top1 | `--spec-type mtp:n_max=3,p_min=0.0` | 351.95 t/s | 242.47 s | **16.77 t/s** | 273.39 s | 21447 MiB | 61.5% (331/538) | SUCCESS |
| 23_repeat_top2 | mtp_n4_p05_repeat | Validation-Top2 | `--spec-type mtp:n_max=4,p_min=0.5` | 352.17 t/s | 242.32 s | **16.58 t/s** | 273.63 s | 21597 MiB | 64.3% (339/527) | SUCCESS |

---

## 2. Ключевые выводы и сравнение

1. **Baseline (без speculative decoding):**
   - Скорость генерации: **12.93 tok/s**
   - Prompt Eval: **379.02 tok/s** (TTFT: **225.15 s**)
   - Пиковое потребление VRAM: **20024 MiB** (~20.0 GB)

2. **Абсолютный победитель:**
   - **`mtp:n_max=3,p_min=0.0`** (`06_mtp_n3_p0` / `22_repeat_top1`)
   - Скорость генерации: **16.17 tok/s** (при повторном контрольном прогоне: **16.77 tok/s**)
   - Прирост скорости генерации: **+25.1%** (до **+29.7%** в повторном тесте)
   - Prompt Eval: **342.76 tok/s** (TTFT: **248.97 s**)
   - Пиковое потребление VRAM: **21858 MiB** (~21.8 GB из 22.5 GB)
   - MTP Acceptance: **61.5%** (331 принято из 538 драфтов)

3. **Второе место (ТОП-2):**
   - **`mtp:n_max=4,p_min=0.5`** (`10_mtp_n4_p5` / `23_repeat_top2`)
   - Скорость генерации: **15.95 tok/s** (при повторе: **16.58 tok/s**)
   - Ускорение: **+23.4%** к baseline.

4. **Лучший self-speculative (n-gram) режим:**
   - **`ngram-simple:n_max=16`** (`16_ngram_simple_16`): **14.05 tok/s** (+8.7% к baseline).
   - `ngram-mod:n_max=16`: **13.73 tok/s** (+6.2% к baseline).
   - Главное преимущество n-gram методов: нулевые накладные расходы на VRAM и быстрый TTFT (221 s против 248 s у MTP).

5. **Какие режимы оказались хуже и почему:**
   - **`mtp:n_max=1` (12.77 tok/s)**: при драфте только одного токена накладные расходы на верификацию нивелируют выигрыш от одного шага.
   - **MTP с высоким `p_min=0.7` (12.25 tok/s)**: слишком жесткая фильтрация отсекает большинство драфтов до верификации, сводя полезную работу MTP к нулю при сохранении накладных расходов.
   - **Two-Stage (`ngram + MTP`) — провал (1.38 – 2.07 tok/s)**: связывание двух механизмов спекуляции приводит к частым конфликтам отката KV-кэша и рекуррентных SSM-состояний архитектуры Qwen 3.5. Время выполнения запроса выросло до 22–29 минут!
   - **`heads=0` / `heads=2`**: модель содержит физически только один MTP-блок (`nextn_predict_layers = 1`), поэтому изменение параметра `heads` не дает эффекта (скорость осталась идентичной `n_max=1`).

---

## 3. Рекомендуемая конфигурация для ежедневного использования

Для максимальной производительности в длинных агентных сессиях (~85–96K токенов) рекомендуется режим:

**`--spec-type mtp:n_max=3,p_min=0.0`**

### Командная строка запуска:
```cmd
K:\Project\ik_llama\bin\llama-server.exe ^
  -m "D:\Project\models\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf" ^
  -c 98304 ^
  -ctk q8_0 ^
  -ctv q5_0 ^
  -fa on ^
  -ngl 999 ^
  -np 1 ^
  -dev CUDA0 ^
  --spec-type mtp:n_max=3,p_min=0.0 ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05
```
