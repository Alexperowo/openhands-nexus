# Ornith-1.5-35B-A3B MTP & 96K Benchmark Results

## Summary

- **Model**: `K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf`
- **Architecture**: `qwen35moe` (256x2.6B MoE, Hybrid Attention, Next-N MTP = 1 head)
- **CUDA Device**: NVIDIA GeForce RTX 2080 Ti (CUDA Compute 7.5, 22 GB / 22,528 MiB VRAM)
- **Backend**: `K:\Project\ik_llama\bin\llama-server.exe` (commit `3c58ae3`)

---

## 1. Multi-Turn Dialog with KV Cache Reuse (96K Context, ~84K Active Context)

Тест реальной сессии: один сервер, холодный старт на 84 005 токенах, затем 2 последовательных follow-up сообщения в той же сессии с добавлением только коротких реплик пользователя (~40-50 токенов).

| Ход диалога | Метрика | MTP OFF (Базовый) | MTP n1 p0.75 | Разница / Выигрыш |
| :--- | :--- | :---: | :---: | :---: |
| **Ход 1: Cold Start** (~84K prompt, 250 gen) | **Prompt eval**<br>Prompt speed<br>Generation speed<br>**Полный Wall Time**<br>Peak VRAM | **84,005 tok / 81.10 s**<br>1035.9 tok/s<br>34.58 tok/s<br>**88.69 s**<br>19,333 MiB | **84,005 tok / 98.70 s**<br>851.1 tok/s<br>39.73 tok/s<br>**105.36 s**<br>20,679 MiB | MTP медленнее на первом холодном старте на +16.67 с из-за более низкого PP (851 vs 1035 tok/s). |
| **Ход 2: Follow-up 1** (KV Reuse, 200 gen) | **Новых токенов промпта**<br>Prompt eval time<br>Generation speed<br>**Полный Wall Time**<br>Peak VRAM | **50 токенов (84K reused)**<br>195 ms<br>34.59 tok/s<br>**6.34 s**<br>19,337 MiB | **50 токенов (84K reused)**<br>231 ms<br>43.62 tok/s<br>**5.23 s**<br>20,685 MiB | **MTP быстрее на 1.11 с (-17.5% latency)** благодаря ускорению генерации с 34.6 до 43.6 tok/s. |
| **Ход 3: Follow-up 2** (KV Reuse, 200 gen) | **Новых токенов промпта**<br>Prompt eval time<br>Generation speed<br>**Полный Wall Time**<br>Peak VRAM | **40 токенов (84K reused)**<br>175 ms<br>34.56 tok/s<br>**6.37 s**<br>19,337 MiB | **43 токена (84K reused)**<br>214 ms<br>37.26 tok/s<br>**5.96 s**<br>20,685 MiB | **MTP быстрее на 0.41 с (-6.4% latency)** благодаря ускорению генерации с 34.6 до 37.3 tok/s. |

### Подтверждение KV / Prefix Cache Reuse
По логам `llama-server.exe`:
- На ходах 2 и 3 пересчитывались исключительно дельта-токены новых реплик (40–50 токенов за 175–231 мс).
- Все 84 000+ токенов контекста полностью повторно использовались из KV-кэша (`slot create_check: created context checkpoint ... / 100% cache hit`).
- **Вывод по цели**: при существующем 84K контексте MTP **реально уменьшает latency** каждого последующего хода (на 6–18%), так как время обработки промпта становится ничтожно малым (~0.2 с) и общее время ответа на 97% определяется чистой генерацией.

---

## 2. MTP Sweep Matrix (16K Context, 256 generated tokens)

| Режим | Параметры спекуляции | Gen tok/s | PP tok/s | Drafted | Accepted | Acceptance % | Peak VRAM | Статус |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **baseline-no-mtp** | None (MTP OFF) | 57.00 | 447.15 | 0 | 0 | 0.0% | 18,583 MiB | **PASS** |
| **mtp-n1-p075 (TOP-1)** | `--spec-type mtp:n_max=1,p_min=0.75` | **57.06 – 66.84** | 168.14 | 153 | 101 | **66.0%** | 19,625 MiB | **PASS** |
| **mtp-author (TOP-2)** | `--spec-type ngram-mod:n_min=8,n_max=24,ngram_size_n=48 --spec-type mtp:n_max=1,p_min=0.75` | **54.00** | 161.36 | 153 | 101 | **66.0%** | 21,071 MiB | **PASS** |
| **mtp-n3-p0** | `--spec-type mtp:n_max=3,p_min=0.0` | 52.10 | 179.32 | 421 | 114 | 27.1% | 19,751 MiB | **PASS** |
| **mtp-n3-p075** | `--spec-type mtp:n_max=3,p_min=0.75` | 51.40 | 167.99 | 157 | 98 | 62.4% | 19,751 MiB | **PASS** |
| **mtp-n2-p0** | `--spec-type mtp:n_max=2,p_min=0.0` | 49.85 | 176.82 | 287 | 111 | 38.7% | 19,689 MiB | **PASS** |
| **mtp-n2-p075** | `--spec-type mtp:n_max=2,p_min=0.75` | 48.99 | 176.00 | 157 | 98 | 62.4% | 19,689 MiB | **PASS** |

---

## 3. Vision Smoke Test (`mmproj-Ornith-1.5-35B-BF16.gguf`)

Тестировался на скриншоте Android-планшета `initial-screen.png` (высокое разрешение 1080x2400).

- **Vision без MTP (16K context)**: **PASS** (100% функционален, корректно распознал русскоязычный чат, статус-бар 20:18 и плашку «Gemini 3.8 Flash High»).
- **Vision + Best MTP (16K context)**: **PASS** (100% совместим, выделил кнопки навигации и чата; драфт-принятие **69.6%**, 32 из 46 токенов).
- **VRAM Headroom Warning**: пиковое потребление памяти в режиме Vision + MTP составило **22,034 MiB** из 22,528 MiB. Запас по VRAM небольшой — около **0.48 GB (~500 MB)**.
- **Ограничение контекста для Vision**: для картинок высокого разрешения контекст должен быть не менее `-c 16384` (при `-c 4096` патчи картинки превышают размер окна).
- **96K + Vision**: **NOT TESTED** (совместный запуск полного окна 98K и Vision не тестировался; при 98K VRAM составляет 20.7 GB, добавление ~2 GB проектора и vision-буферов приведет к OOM на 22GB GPU).

---

## 4. Production Launcher

Финальный лаунчер: `K:\Project\LLM-tests\BEST-ORNITH15-96K.cmd`
Конфигурация (сохранён победитель `mtp:n_max=1,p_min=0.75`):
```cmd
@echo off
set "MODEL=K:\Project\Models\Ornith-1.5-35B-MTP-19G-ICE.gguf"
set "SERVER=K:\Project\ik_llama\bin\llama-server.exe"

"%SERVER%" ^
  -m "%MODEL%" ^
  -c 98304 ^
  -ctk q8_0 ^
  -ctv q5_0 ^
  -fa on ^
  -ngl 999 ^
  -np 1 ^
  -dev CUDA0 ^
  --spec-type mtp:n_max=1,p_min=0.75 ^
  --jinja ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --temp 0.7 ^
  --top-p 0.8 ^
  --min-p 0.05
```
