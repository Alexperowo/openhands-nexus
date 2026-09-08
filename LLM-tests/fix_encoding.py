# -*- coding: utf-8 -*-
import os, json, csv

opt_dir = r"K:\Project\LLM-tests\optimization"
json_path = os.path.join(opt_dir, "optimization.json")
md_path = os.path.join(opt_dir, "FINAL-OPTIMIZATION.md")
cmd_path = r"K:\Project\LLM-tests\BEST-QWEN38-96K.cmd"

with open(json_path, "r", encoding="utf-8-sig") as f:
    data = json.load(f)

baseline = next(d for d in data if d["TestId"] == "01_baseline")
top1 = next(d for d in data if d["TestId"] == "06_mtp_n3_p0")
top1_repeat = next(d for d in data if d["TestId"] == "22_repeat_top1")
top2 = next(d for d in data if d["TestId"] == "10_mtp_n4_p5")
top2_repeat = next(d for d in data if d["TestId"] == "23_repeat_top2")
best_ngram = next(d for d in data if d["TestId"] == "16_ngram_simple_16")

speedup_pct = round(((top1["GenSpeed_TokSec"] - baseline["GenSpeed_TokSec"]) / baseline["GenSpeed_TokSec"]) * 100.0, 1)
repeat_speedup_pct = round(((top1_repeat["GenSpeed_TokSec"] - baseline["GenSpeed_TokSec"]) / baseline["GenSpeed_TokSec"]) * 100.0, 1)

lines = []
lines.append("# Итоговый отчёт оптимизации: Qwen3.8-27B Opus-Distill-v2 (~85.3K Context)\n")
lines.append("**Конфигурация тестового стенда:**")
lines.append("- **Модель**: `D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf` (архитектура `qwen35` hybrid Attention + SSM)")
lines.append("- **Backend**: `ik_llama.cpp` (коммит `3c58ae3`, сборка с поддержкой recurrent checkpoints и MTP)")
lines.append("- **GPU**: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM, 22528 MiB)")
lines.append("- **Контекст**: `n_ctx = 98304` (96K), реальное заполнение промпта: **85 337 токенов**")
lines.append("- **KV Cache**: `K = q8_0`, `V = q5_0`")
lines.append("- **Flash Attention**: `ON` (`-fa on`)")
lines.append("- **Параллелизм**: `1` (`-np 1`)")
lines.append("- **Параметры генерации**: 512 токенов, `seed = 42`, `temp = 0.7`, `top_p = 0.8`, `min_p = 0.05`\n")
lines.append("---\n")
lines.append("## 1. Сводная таблица всех 23 протестированных конфигураций\n")
lines.append("| № | Тест | Категория | Флаги speculative | Prompt Eval | TTFT | Gen Speed | Время запроса | Пик VRAM | MTP Acceptance | Статус |")
lines.append("| :-: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

for d in data:
    spec = f"`{d['SpecFlags']}`" if d['SpecFlags'] else "*(нет)*"
    acc = f"{d['AcceptanceRate']} ({d['AcceptedDrafts']}/{d['TotalDrafts']})" if d.get('TotalDrafts', 0) > 0 else d['AcceptanceRate']
    lines.append(f"| {d['TestId']} | {d['TestName']} | {d['Category']} | {spec} | {d['PromptEval_TokSec']} t/s | {d['TTFT_Sec']} s | **{d['GenSpeed_TokSec']} t/s** | {d['TotalTime_Sec']} s | {d['PeakVRAM_MiB']} MiB | {acc} | {d['Status']} |")

lines.append("\n---\n")
lines.append("## 2. Ключевые выводы и сравнение\n")
lines.append(f"1. **Baseline (без speculative decoding):**")
lines.append(f"   - Скорость генерации: **{baseline['GenSpeed_TokSec']} tok/s**")
lines.append(f"   - Prompt Eval: **{baseline['PromptEval_TokSec']} tok/s** (TTFT: **{baseline['TTFT_Sec']} s**)")
lines.append(f"   - Пиковое потребление VRAM: **{baseline['PeakVRAM_MiB']} MiB** (~20.0 GB)\n")

lines.append(f"2. **Абсолютный победитель:**")
lines.append(f"   - **`mtp:n_max=3,p_min=0.0`** (`06_mtp_n3_p0` / `22_repeat_top1`)")
lines.append(f"   - Скорость генерации: **{top1['GenSpeed_TokSec']} tok/s** (при повторном контрольном прогоне: **{top1_repeat['GenSpeed_TokSec']} tok/s**)")
lines.append(f"   - Прирост скорости генерации: **+{speedup_pct}%** (до **+{repeat_speedup_pct}%** в повторном тесте)")
lines.append(f"   - Prompt Eval: **{top1['PromptEval_TokSec']} tok/s** (TTFT: **{top1['TTFT_Sec']} s**)")
lines.append(f"   - Пиковое потребление VRAM: **{top1['PeakVRAM_MiB']} MiB** (~21.8 GB из 22.5 GB)")
lines.append(f"   - MTP Acceptance: **{top1['AcceptanceRate']}** ({top1['AcceptedDrafts']} принято из {top1['TotalDrafts']} драфтов)\n")

lines.append(f"3. **Второе место (ТОП-2):**")
lines.append(f"   - **`mtp:n_max=4,p_min=0.5`** (`10_mtp_n4_p5` / `23_repeat_top2`)")
lines.append(f"   - Скорость генерации: **{top2['GenSpeed_TokSec']} tok/s** (при повторе: **{top2_repeat['GenSpeed_TokSec']} tok/s**)")
lines.append(f"   - Ускорение: **+23.4%** к baseline.\n")

lines.append(f"4. **Лучший self-speculative (n-gram) режим:**")
lines.append(f"   - **`ngram-simple:n_max=16`** (`16_ngram_simple_16`): **{best_ngram['GenSpeed_TokSec']} tok/s** (+8.7% к baseline).")
lines.append(f"   - `ngram-mod:n_max=16`: **13.73 tok/s** (+6.2% к baseline).")
lines.append(f"   - Главное преимущество n-gram методов: нулевые накладные расходы на VRAM и быстрый TTFT (221 s против 248 s у MTP).\n")

lines.append("5. **Какие режимы оказались хуже и почему:**")
lines.append("   - **`mtp:n_max=1` (12.77 tok/s)**: при драфте только одного токена накладные расходы на верификацию нивелируют выигрыш от одного шага.")
lines.append("   - **MTP с высоким `p_min=0.7` (12.25 tok/s)**: слишком жесткая фильтрация отсекает большинство драфтов до верификации, сводя полезную работу MTP к нулю при сохранении накладных расходов.")
lines.append("   - **Two-Stage (`ngram + MTP`) — провал (1.38 – 2.07 tok/s)**: связывание двух механизмов спекуляции приводит к частым конфликтам отката KV-кэша и рекуррентных SSM-состояний архитектуры Qwen 3.5. Время выполнения запроса выросло до 22–29 минут!")
lines.append("   - **`heads=0` / `heads=2`**: модель содержит физически только один MTP-блок (`nextn_predict_layers = 1`), поэтому изменение параметра `heads` не дает эффекта (скорость осталась идентичной `n_max=1`).\n")

lines.append("---\n")
lines.append("## 3. Рекомендуемая конфигурация для ежедневного использования\n")
lines.append("Для максимальной производительности в длинных агентных сессиях (~85–96K токенов) рекомендуется режим:\n")
lines.append("**`--spec-type mtp:n_max=3,p_min=0.0`**\n")
lines.append("### Командная строка запуска:")
lines.append("```cmd")
lines.append("K:\\Project\\ik_llama\\bin\\llama-server.exe ^")
lines.append("  -m \"D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf\" ^")
lines.append("  -c 98304 ^")
lines.append("  -ctk q8_0 ^")
lines.append("  -ctv q5_0 ^")
lines.append("  -fa on ^")
lines.append("  -ngl 999 ^")
lines.append("  -np 1 ^")
lines.append("  -dev CUDA0 ^")
lines.append("  --spec-type mtp:n_max=3,p_min=0.0 ^")
lines.append("  --host 127.0.0.1 ^")
lines.append("  --port 8080 ^")
lines.append("  --temp 0.7 ^")
lines.append("  --top-p 0.8 ^")
lines.append("  --min-p 0.05")
lines.append("```\n")

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

best_cmd = """@echo off
set "MODEL=D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf"
set "SERVER=K:\\Project\\ik_llama\\bin\\llama-server.exe"

"%SERVER%" ^
  -m "%MODEL%" ^
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
"""

with open(cmd_path, "w", encoding="utf-8") as f:
    f.write(best_cmd)

print("SUCCESS: Rewritten with clean UTF-8 encoding!")