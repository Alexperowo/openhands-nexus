# Qwen3-Next-80B Reasoning Control & Profile Specifications

## 1. Native Budget Control Mechanism (Official llama.cpp b10816)

- **CLI Flag**: `--reasoning-budget-message <MESSAGE>`
  - Injected directly before `</think>` when the reasoning budget is exhausted.
  - Verified prompt message: `"Conclude reasoning immediately and output the final answer now."`
- **Per-Request Budget Parameter**: `"thinking_budget_tokens": <N>` in `/v1/chat/completions`.
- **Reasoning Extraction**: `--reasoning-format deepseek` separates thoughts into `message.reasoning_content` and final answer into `message.content`.
- **Loop Prevention**: With this native mechanism, Qwen3-Next **stops thinking immediately** upon budget exhaustion, transitions cleanly to structured code/prose, and finishes with `finish_reason: stop`.

## 2. Production Reasoning Profiles (Tested with MTP_Q4, ngl=26)

| Profile | Target Use Case | `thinking_budget_tokens` | `max_tokens` | Turn Latency | TG Speed | Finish Reason | MTP Accepted |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **NEXT-NORMAL** | Deep Code Review & Refactoring | 1024 | 4096 | **131.36s** | 17.94 tok/s | `stop` | 972 |
| **NEXT-DEEP** | Deep Code Review & Refactoring | 2048 | 6144 | **174.99s** | 17.65 tok/s | `stop` | 1273 |

## 3. Deployment Configuration
```cmd
llama-server.exe ^
  -m "K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf" ^
  -md "K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-MTP-ONLY-Q4_K_M.gguf" ^
  --spec-type draft-mtp --spec-draft-n-max 1 ^
  -ngl 26 -c 16384 -fa on -ctk q8_0 -ctv q8_0 -dev CUDA0 -np 1 -t 6 ^
  --reasoning-format deepseek ^
  --reasoning-budget-message "Conclude reasoning immediately and output the final answer now." ^
  --host 127.0.0.1 --port 8080
```
