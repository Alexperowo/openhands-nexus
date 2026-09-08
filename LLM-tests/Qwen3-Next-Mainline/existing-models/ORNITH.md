# Ornith-1.5-35B Evaluation on Official llama.cpp b10816

## 1. 16K Benchmark (MTP OFF vs MTP ON)

| Mode | PP Speed (tok/s) | TG Speed (tok/s) | Wall Time (s) | MTP Drafts Accepted | VRAM Peak (MiB) | RAM Peak (MiB) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **MTP OFF** | 2.61 tok/s | **74.01 tok/s** | 24.11s | N/A | 18,282 MiB | 21,613 MiB |
| **MTP ON (`n_max=1, p_min=0.75`)** | 102.06 tok/s | **54.72 tok/s** | 9.79s | **133 tokens** | 18,854 MiB | 22,064 MiB |

> [!NOTE]
> In raw 16K decoding, unconstrained generation (MTP OFF) achieves higher throughput (74.01 tok/s) than MTP ON (54.72 tok/s) due to speculative verification overhead on the MoE architecture. However, MTP draft acceptance is operational (133 accepted tokens).

## 2. Dynamic Thinking & Reasoning Controls
- **Thinking Enabled (`thinking_budget_tokens: 128`)**: **PASS**
  - Prompt: *"Which is bigger: 9.11 or 9.9?"*
  - Message content: `**9.9 is bigger.** Here's why: Both numbers have the same whole-number part (9)...`
  - Reasoning trace: Captured cleanly in `reasoning_content` (402 characters).
- **Thinking Suppressed (`thinking_budget_tokens: 0`)**: **PASS**
  - Prompt: *"What is 25 * 25? Output only the number."*
  - Message content: `625`
  - Control mechanism: Enforced reliably using native `--reasoning-budget-message "Conclude reasoning immediately and output the final answer now."`.

## 3. OpenAI Function / Tool Calling
- **Status**: **PASS**
- Tested payload: Function call definition `lookup_stock_price` for query *"Check the stock price for NVDA."*
- Response: Native `tool_calls` structured object:
  - Function: `lookup_stock_price`
  - Arguments: `{"ticker":"NVDA"}`
- Requires: `--jinja` flag enabled on `llama-server`.

## 4. Vision Smoke Test with mmproj
- **Projector**: `K:\Project\Models\mmproj-Ornith-1.5-35B-BF16.gguf` (BF16, 5.8 GB)
- **Status**: **PASS**
- Multimodal initialization time: 42.1s
- Test image: 1x1 solid red PNG sent via standard OpenAI format (`image_url: {"url": "data:image/png;base64,..."}`).
- Model response: `Red`
- Peak VRAM during vision inference: **19,332 MiB** (fits completely within 24 GB).

## 5. 96K Long-Context Performance
- **Configuration**: `-c 98304 -ctk q8_0 -ctv q5_0 -ngl 999 -fa on --spec-type draft-mtp --spec-draft-n-max 1 --spec-draft-p-min 0.75`
- **Cold Prompt Processing (~11,332 tokens)**:
  - PP Speed: **41.65 tok/s** (TTFT: 272.07s)
  - TG Speed: **12.39 tok/s**
  - Draft Acceptance: **88.6%** (31 accepted / 35 generated)
- **KV-Cache Reuse Follow-up**:
  - TTFT: **6.98s** (11,328 cached tokens reused, 124 computation graphs reused)
  - TG Speed: **12.26 tok/s**
  - Draft Acceptance: **82.9%** (29 accepted / 35 generated)
- **Memory Footprint**:
  - Base 96K VRAM: 19,750 MiB
  - Peak 96K VRAM: **19,794 MiB** (leaves 4.0+ GB free VRAM headroom)
  - Peak RAM: 22,291 MiB

## 6. Comparison: Official llama.cpp b10816 vs ik_llama (commit 3c58ae3)
- **Embedded MTP**: Fully operational on official `b10816` (`--spec-type draft-mtp`).
- **Vision (mmproj)**: Fully functional with zero errors on `b10816`.
- **Tool Calling & Thinking Control**: Works out-of-the-box with `--jinja` and `--reasoning-budget-message`.
- **Prompt Processing Speed Gap**: On long contexts (96K), official `llama.cpp` processes prompts at ~42 tok/s vs `ik_llama`'s ~800 tok/s. This is because `ik_llama` contains custom MoE batching CUDA kernels by ikawrakow that are not yet part of mainline `llama.cpp`. Once the prompt is cached, KV reuse drops latency to ~7s and generation runs at 12-74 tok/s.