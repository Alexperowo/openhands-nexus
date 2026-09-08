# Qwen3.8-27B-Opus Evaluation on Official llama.cpp b10816

## 1. 16K Benchmark (MTP OFF vs MTP ON)
- **MTP OFF**: PP = **146.70 tok/s**, TG = **22.22 tok/s**, VRAM = 16,732 MiB
- **MTP ON (`n_max=3`)**: PP = **145.70 tok/s**, TG = **23.91 tok/s** (+7.6% speedup), Draft Accepted = **296 tokens**, VRAM = 16,980 MiB

## 2. Functional Capabilities
- **Non-Thinking / Direct**: **PASS** (Pure content returned without reasoning contamination)
- **Tool Calling (OpenAI format)**: `PASS`
  - Function: `lookup_stock_price`
  - Arguments: `{"ticker":"NVDA"}`
  - Requires `--jinja` flag in official llama.cpp for tool call grammar synthesis.

## 3. 96K Long-Context Performance
- **Cold Prompt Processing**: **47.86 tok/s** (3838 tokens in 80.19s)
- **Cold Generation**: **9.46 tok/s** (MTP Accepted: 37/None)
- **KV-Cache Reuse Follow-up**: **1.51s TTFT** (TG: **9.61 tok/s**, MTP Accepted: 39/None)
- **Memory Footprint**: Peak VRAM = **20258 MiB** (leaves 3.5+ GB free), Peak RAM = **21612 MiB**

## 4. Verdict on Qwen3.8-27B-Opus
- Official `llama.cpp b10816` is **fully compatible** and achieves identical performance to `ik_llama commit 3c58ae3`.
- Embedded MTP works natively via `--spec-type draft-mtp --spec-draft-n-max 3`.
- Tool calling and KV reuse work out-of-the-box.
