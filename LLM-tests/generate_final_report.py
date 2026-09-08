import os, glob, re, json, csv

opt_dir = r"K:\Project\LLM-tests\optimization"
csv_path = os.path.join(opt_dir, "optimization.csv")
json_path = os.path.join(opt_dir, "optimization.json")
md_path = os.path.join(opt_dir, "FINAL-OPTIMIZATION.md")
cmd_path = r"K:\Project\LLM-tests\BEST-QWEN38-96K.cmd"

with open(json_path, "r", encoding="utf-8-sig") as f:
    data = json.load(f)

# Re-scan logs to get the MAIN request acceptance stats (last occurrence in each log)
for item in data:
    log_file = os.path.join(opt_dir, f"{item['TestName']}.log")
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8", errors="ignore") as lf:
            content = lf.read()
        # Find all occurrences of draft acceptance rate
        matches = re.findall(r"draft acceptance rate = ([0-9\.]+)\s*\(\s*(\d+)\s+accepted\s*/\s*(\d+)\s+generated\)", content)
        if matches:
            last_m = matches[-1]
            rate_pct = round(float(last_m[0]) * 100.0, 1)
            item["AcceptanceRate"] = f"{rate_pct}%"
            item["AcceptedDrafts"] = int(last_m[1])
            item["TotalDrafts"] = int(last_m[2])
        else:
            simple_matches = re.findall(r"draft acceptance rate = ([0-9\.]+)", content)
            if simple_matches:
                rate_pct = round(float(simple_matches[-1]) * 100.0, 1)
                item["AcceptanceRate"] = f"{rate_pct}%"

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Update CSV
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
    writer.writeheader()
    writer.writerows(data)

# Find key benchmarks
baseline = next(d for d in data if d["TestId"] == "01_baseline")
top1 = next(d for d in data if d["TestId"] == "06_mtp_n3_p0")
top1_repeat = next(d for d in data if d["TestId"] == "22_repeat_top1")
top2 = next(d for d in data if d["TestId"] == "10_mtp_n4_p5")
top2_repeat = next(d for d in data if d["TestId"] == "23_repeat_top2")
best_ngram = next(d for d in data if d["TestId"] == "16_ngram_simple_16")

speedup_pct = round(((top1["GenSpeed_TokSec"] - baseline["GenSpeed_TokSec"]) / baseline["GenSpeed_TokSec"]) * 100.0, 1)
repeat_speedup_pct = round(((top1_repeat["GenSpeed_TokSec"] - baseline["GenSpeed_TokSec"]) / baseline["GenSpeed_TokSec"]) * 100.0, 1)

md = f"""# РС‚РѕРіРѕРІС‹Р№ РѕС‚С‡С‘С‚ РѕРїС‚РёРјРёР·Р°С†РёРё: Qwen3.8-27B Opus-Distill-v2 (~85.3K Context)

**РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ С‚РµСЃС‚РѕРІРѕРіРѕ СЃС‚РµРЅРґР°:**
- **РњРѕРґРµР»СЊ**: `D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf` (Р°СЂС…РёС‚РµРєС‚СѓСЂР° `qwen35` hybrid Attention + SSM)
- **Backend**: `ik_llama.cpp` (РєРѕРјРјРёС‚ `3c58ae3`, СЃР±РѕСЂРєР° СЃ РїРѕРґРґРµСЂР¶РєРѕР№ recurrent checkpoints Рё MTP)
- **GPU**: NVIDIA GeForce RTX 2080 Ti (22 GB VRAM, 22528 MiB)
- **РљРѕРЅС‚РµРєСЃС‚**: `n_ctx = 98304` (96K), СЂРµР°Р»СЊРЅРѕРµ Р·Р°РїРѕР»РЅРµРЅРёРµ РїСЂРѕРјРїС‚Р°: **85 337 С‚РѕРєРµРЅРѕРІ**
- **KV Cache**: `K = q8_0`, `V = q5_0`
- **Flash Attention**: `ON` (`-fa on`)
- **РџР°СЂР°Р»Р»РµР»РёР·Рј**: `1` (`-np 1`)
- **РџР°СЂР°РјРµС‚СЂС‹ РіРµРЅРµСЂР°С†РёРё**: 512 С‚РѕРєРµРЅРѕРІ, `seed = 42`, `temp = 0.7`, `top_p = 0.8`, `min_p = 0.05`

---

## 1. РЎРІРѕРґРЅР°СЏ С‚Р°Р±Р»РёС†Р° РІСЃРµС… 23 РїСЂРѕС‚РµСЃС‚РёСЂРѕРІР°РЅРЅС‹С… РєРѕРЅС„РёРіСѓСЂР°С†РёР№

| в„– | РўРµСЃС‚ | РљР°С‚РµРіРѕСЂРёСЏ | Р¤Р»Р°РіРё speculative | Prompt Eval | TTFT | Gen Speed | Р’СЂРµРјСЏ Р·Р°РїСЂРѕСЃР° | РџРёРє VRAM | MTP Acceptance | РЎС‚Р°С‚СѓСЃ |
| :-: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""

for d in data:
    spec = f"`{d['SpecFlags']}`" if d['SpecFlags'] else "*(РЅРµС‚)*"
    acc = f"{d['AcceptanceRate']} ({d['AcceptedDrafts']}/{d['TotalDrafts']})" if d['TotalDrafts'] > 0 else d['AcceptanceRate']
    md += f"| {d['TestId']} | {d['TestName']} | {d['Category']} | {spec} | {d['PromptEval_TokSec']} t/s | {d['TTFT_Sec']} s | **{d['GenSpeed_TokSec']} t/s** | {d['TotalTime_Sec']} s | {d['PeakVRAM_MiB']} MiB | {acc} | {d['Status']} |\n"

md += f"""
---

## 2. РљР»СЋС‡РµРІС‹Рµ РІС‹РІРѕРґС‹ Рё СЃСЂР°РІРЅРµРЅРёРµ

1. **Baseline (Р±РµР· speculative decoding):**
   - РЎРєРѕСЂРѕСЃС‚СЊ РіРµРЅРµСЂР°С†РёРё: **{baseline['GenSpeed_TokSec']} tok/s**
   - Prompt Eval: **{baseline['PromptEval_TokSec']} tok/s** (TTFT: **{baseline['TTFT_Sec']} s**)
   - РџРёРєРѕРІРѕРµ РїРѕС‚СЂРµР±Р»РµРЅРёРµ VRAM: **{baseline['PeakVRAM_MiB']} MiB** (~20.0 GB)

2. **РђР±СЃРѕР»СЋС‚РЅС‹Р№ РїРѕР±РµРґРёС‚РµР»СЊ:**
   - **`mtp:n_max=3,p_min=0.0`** (`06_mtp_n3_p0` / `22_repeat_top1`)
   - РЎРєРѕСЂРѕСЃС‚СЊ РіРµРЅРµСЂР°С†РёРё: **{top1['GenSpeed_TokSec']} tok/s** (РїСЂРё РїРѕРІС‚РѕСЂРЅРѕРј РєРѕРЅС‚СЂРѕР»СЊРЅРѕРј РїСЂРѕРіРѕРЅРµ: **{top1_repeat['GenSpeed_TokSec']} tok/s**)
   - РџСЂРёСЂРѕСЃС‚ СЃРєРѕСЂРѕСЃС‚Рё РіРµРЅРµСЂР°С†РёРё: **+{speedup_pct}%** (РґРѕ **+{repeat_speedup_pct}%** РІ РїРѕРІС‚РѕСЂРЅРѕРј С‚РµСЃС‚Рµ)
   - Prompt Eval: **{top1['PromptEval_TokSec']} tok/s** (TTFT: **{top1['TTFT_Sec']} s**)
   - РџРёРєРѕРІРѕРµ РїРѕС‚СЂРµР±Р»РµРЅРёРµ VRAM: **{top1['PeakVRAM_MiB']} MiB** (~21.8 GB РёР· 22.5 GB)
   - MTP Acceptance: **{top1['AcceptanceRate']}** ({top1['AcceptedDrafts']} РїСЂРёРЅСЏС‚Рѕ РёР· {top1['TotalDrafts']} РґСЂР°С„С‚РѕРІ)

3. **Р’С‚РѕСЂРѕРµ РјРµСЃС‚Рѕ (РўРћРџ-2):**
   - **`mtp:n_max=4,p_min=0.5`** (`10_mtp_n4_p5` / `23_repeat_top2`)
   - РЎРєРѕСЂРѕСЃС‚СЊ РіРµРЅРµСЂР°С†РёРё: **{top2['GenSpeed_TokSec']} tok/s** (РїСЂРё РїРѕРІС‚РѕСЂРµ: **{top2_repeat['GenSpeed_TokSec']} tok/s**)
   - РЈСЃРєРѕСЂРµРЅРёРµ: **+23.4%** Рє baseline.

4. **Р›СѓС‡С€РёР№ self-speculative (n-gram) СЂРµР¶РёРј:**
   - **`ngram-simple:n_max=16`** (`16_ngram_simple_16`): **{best_ngram['GenSpeed_TokSec']} tok/s** (+8.7% Рє baseline).
   - `ngram-mod:n_max=16`: **13.73 tok/s** (+6.2% Рє baseline).
   - Р“Р»Р°РІРЅРѕРµ РїСЂРµРёРјСѓС‰РµСЃС‚РІРѕ n-gram РјРµС‚РѕРґРѕРІ: РЅСѓР»РµРІС‹Рµ РЅР°РєР»Р°РґРЅС‹Рµ СЂР°СЃС…РѕРґС‹ РЅР° VRAM Рё Р±С‹СЃС‚СЂС‹Р№ TTFT (221 s РїСЂРѕС‚РёРІ 248 s Сѓ MTP).

5. **РљР°РєРёРµ СЂРµР¶РёРјС‹ РѕРєР°Р·Р°Р»РёСЃСЊ С…СѓР¶Рµ Рё РїРѕС‡РµРјСѓ:**
   - **`mtp:n_max=1` (12.77 tok/s)**: РїСЂРё РґСЂР°С„С‚Рµ С‚РѕР»СЊРєРѕ РѕРґРЅРѕРіРѕ С‚РѕРєРµРЅР° РЅР°РєР»Р°РґРЅС‹Рµ СЂР°СЃС…РѕРґС‹ РЅР° РІРµСЂРёС„РёРєР°С†РёСЋ РЅРёРІРµР»РёСЂСѓСЋС‚ РІС‹РёРіСЂС‹С€ РѕС‚ РѕРґРЅРѕРіРѕ С€Р°РіР°.
   - **MTP СЃ РІС‹СЃРѕРєРёРј `p_min=0.7` (12.25 tok/s)**: СЃР»РёС€РєРѕРј Р¶РµСЃС‚РєР°СЏ С„РёР»СЊС‚СЂР°С†РёСЏ РѕС‚СЃРµРєР°РµС‚ Р±РѕР»СЊС€РёРЅСЃС‚РІРѕ РґСЂР°С„С‚РѕРІ РґРѕ РІРµСЂРёС„РёРєР°С†РёРё, СЃРІРѕРґСЏ РїРѕР»РµР·РЅСѓСЋ СЂР°Р±РѕС‚Сѓ MTP Рє РЅСѓР»СЋ РїСЂРё СЃРѕС…СЂР°РЅРµРЅРёРё РЅР°РєР»Р°РґРЅС‹С… СЂР°СЃС…РѕРґРѕРІ.
   - **Two-Stage (`ngram + MTP`) вЂ” РїСЂРѕРІР°Р» (1.38 вЂ“ 2.07 tok/s)**: СЃРІСЏР·С‹РІР°РЅРёРµ РґРІСѓС… РјРµС…Р°РЅРёР·РјРѕРІ СЃРїРµРєСѓР»СЏС†РёРё РїСЂРёРІРѕРґРёС‚ Рє С‡Р°СЃС‚С‹Рј РєРѕРЅС„Р»РёРєС‚Р°Рј РѕС‚РєР°С‚Р° KV-РєСЌС€Р° Рё СЂРµРєСѓСЂСЂРµРЅС‚РЅС‹С… SSM-СЃРѕСЃС‚РѕСЏРЅРёР№ Р°СЂС…РёС‚РµРєС‚СѓСЂС‹ Qwen 3.5. Р’СЂРµРјСЏ РІС‹РїРѕР»РЅРµРЅРёСЏ Р·Р°РїСЂРѕСЃР° РІС‹СЂРѕСЃР»Рѕ РґРѕ 22вЂ“29 РјРёРЅСѓС‚!
   - **`heads=0` / `heads=2`**: РјРѕРґРµР»СЊ СЃРѕРґРµСЂР¶РёС‚ С„РёР·РёС‡РµСЃРєРё С‚РѕР»СЊРєРѕ РѕРґРёРЅ MTP-Р±Р»РѕРє (`nextn_predict_layers = 1`), РїРѕСЌС‚РѕРјСѓ РёР·РјРµРЅРµРЅРёРµ РїР°СЂР°РјРµС‚СЂР° `heads` РЅРµ РґР°РµС‚ СЌС„С„РµРєС‚Р° (СЃРєРѕСЂРѕСЃС‚СЊ РѕСЃС‚Р°Р»Р°СЃСЊ РёРґРµРЅС‚РёС‡РЅРѕР№ `n_max=1`).

---

## 3. Р РµРєРѕРјРµРЅРґСѓРµРјР°СЏ РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ РґР»СЏ РµР¶РµРґРЅРµРІРЅРѕРіРѕ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ

Р”Р»СЏ РјР°РєСЃРёРјР°Р»СЊРЅРѕР№ РїСЂРѕРёР·РІРѕРґРёС‚РµР»СЊРЅРѕСЃС‚Рё РІ РґР»РёРЅРЅС‹С… Р°РіРµРЅС‚РЅС‹С… СЃРµСЃСЃРёСЏС… (~85вЂ“96K С‚РѕРєРµРЅРѕРІ) СЂРµРєРѕРјРµРЅРґСѓРµС‚СЃСЏ СЂРµР¶РёРј:
**`--spec-type mtp:n_max=3,p_min=0.0`**

### РљРѕРјР°РЅРґРЅР°СЏ СЃС‚СЂРѕРєР° Р·Р°РїСѓСЃРєР°:
```cmd
K:\\Project\\ik_llama\\bin\\llama-server.exe ^
  -m "D:\\Project\\models\\Qwen3.8-27B-Opus-Distill-v2-Q4_K_M.gguf" ^
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
"""

with open(md_path, "w", encoding="utf-8-sig") as f:
    f.write(md)

# Generate BEST-QWEN38-96K.cmd
best_cmd_content = f"""@echo off
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

with open(cmd_path, "w", encoding="utf-8-sig") as f:
    f.write(best_cmd_content)

print("Generated FINAL-OPTIMIZATION.md and BEST-QWEN38-96K.cmd successfully!")