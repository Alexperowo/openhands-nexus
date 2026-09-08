# Qwen3-Next-80B Reasoning & Budget Control Analysis

## 1. Supported Control Mechanism in `ik_llama` (commit `3c58ae3`)

- **CLI Flag**: `--reasoning-budget <N>` (`-1` = unrestricted, `0` = immediate end, `N > 0` = token budget).
- **CLI Format**: `--reasoning-format deepseek` (extracts thoughts to `message.reasoning_content`) or `deepseek-legacy`.
- **Per-Request Budget**: **YES, FULLY SUPPORTED** via `"thinking_budget_tokens": <N>` in `/v1/chat/completions` request body (see `src/examples/server/server-common.cpp:908`).
- **Dynamic Switching**: Budget can be changed on every request without restarting the server or reloading the model.
- **Output Structure**: Thoughts are emitted in `choices[0].message.reasoning_content`, and final answer in `choices[0].message.content`.

## 2. Test Results Across Reasoning Profiles

| Profile | Requested Budget | Max Tokens | Generated Tokens | Finish Reason | Wall Time (s) | TG (tok/s) | Valid Completion |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| NEXT-LOW | 1024 | 3072 | 3072 | `length` | 191.72s | 16.02 | **NO (length)** |
| NEXT-MEDIUM | 2048 | 5120 | 5120 | `length` | 321.4s | 15.93 | **NO (length)** |
| NEXT-HIGH | 4096 | 8192 | 8192 | `length` | 520.51s | 15.74 | **NO (length)** |

## 3. Practical Profile Recommendations for OpenHands

- **NEXT-LOW** (`thinking_budget_tokens: 1024`, `max_tokens: 3072`):
  Fast turn-around for standard code modifications, quick script writing, and syntax fixes.
- **NEXT-MEDIUM** (`thinking_budget_tokens: 2048`, `max_tokens: 5120`):
  Recommended default for complex audits, single-file refactoring, and multi-component bug analysis.
- **NEXT-HIGH** (`thinking_budget_tokens: 4096`, `max_tokens: 8192`):
  Heavy escalation profile for architectural reviews, distributed system failure diagnosis, and complex root-cause investigations.
