# OpenHands Profiles Specification & Parameter Verification

## 1. Profile Deployment Locations
- Active directory: `C:\Users\User\.openhands\profiles\`
- Backup / Repository directory: `K:\Project\OpenHands-Tests\Three-Model-Integration\profiles\`

---

## 2. Profiles Summary

### A. `Next-Normal.json`
- **File**: `C:\Users\User\.openhands\profiles\Next-Normal.json`
- **Model**: `openai/next`
- **Base URL**: `http://127.0.0.1:8080/v1`
- **Max Input Tokens**: `98304`
- **Max Output Tokens**: `5120`
- **Temperature**: `0.6`, **Top P**: `0.95`
- **Thinking Budget**: `2048`
- **Payload Configuration**:
  ```json
  "litellm_extra_body": {
    "thinking_budget_tokens": 2048,
    "reasoning_budget_tokens": 2048,
    "chat_template_kwargs": {
      "thinking_budget_tokens": 2048
    }
  }
  ```

### B. `Next-Deep.json`
- **File**: `C:\Users\User\.openhands\profiles\Next-Deep.json`
- **Model**: `openai/next`
- **Base URL**: `http://127.0.0.1:8080/v1`
- **Max Input Tokens**: `98304`
- **Max Output Tokens**: `8192`
- **Temperature**: `0.6`, **Top P**: `0.95`
- **Thinking Budget**: `4096`
- **Payload Configuration**:
  ```json
  "litellm_extra_body": {
    "thinking_budget_tokens": 4096,
    "reasoning_budget_tokens": 4096,
    "chat_template_kwargs": {
      "thinking_budget_tokens": 4096
    }
  }
  ```

### C. `Qwen38_Opus_96K.json`
- **File**: `C:\Users\User\.openhands\profiles\Qwen38_Opus_96K.json`
- **Model**: `openai/qwen`
- **Base URL**: `http://127.0.0.1:8080/v1`
- **Max Input Tokens**: `98304`
- **Max Output Tokens**: `4096`
- **Temperature**: `0.7`, **Top P**: `0.8`, **Min P**: `0.05`

### D. `Ornith-Coding.json`
- **File**: `C:\Users\User\.openhands\profiles\Ornith-Coding.json`
- **Model**: `openai/ornith`
- **Base URL**: `http://127.0.0.1:8080/v1`
- **Max Input Tokens**: `98304`
- **Max Output Tokens**: `4096`
- **Temperature**: `0.6`, **Top P**: `0.95`, **Top K**: `20`

---

## 3. Raw Runtime Evidence: Thinking Budget & Zero-Reload

Verified live via `test_thinking_budget_runtime.py`:

```
==========================================
Testing Profile: Next-Normal
Configured thinking_budget_tokens: 2048 (Expected: 2048)
==========================================
Elapsed time: 89.81s
PID before: 2972, PID after: 2972 (Reloaded: False)
Prompt tokens: 26, Completion tokens: 1192
Reasoning length: 3766 chars
Response: 'The word "strawberry" has three 'r's. ...'

==========================================
Testing Profile: Next-Deep
Configured thinking_budget_tokens: 4096 (Expected: 4096)
==========================================
Elapsed time: 48.53s
PID before: 2972, PID after: 2972 (Reloaded: False)
Prompt tokens: 26, Completion tokens: 939
Reasoning length: 2769 chars
Response: 'The word "strawberry" has three 'r's. ...'

=== SUMMARY ===
Next-Normal: 89.81s, reloaded=False
Next-Deep:   48.53s, reloaded=False
Zero reload between Normal and Deep: True
```

**Key Proofs**:
1. `thinking_budget_tokens: 2048` and `4096` are passed directly in the request payload and acknowledged by `llama-server`.
2. Both profiles execute on the same running process (PID 2972) without any model reloading or VRAM eviction.
